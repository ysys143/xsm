//! The private key never crosses IPC. A process lock prevents two live nodes sharing it.
use crate::{Error, Result};
use base64::{Engine, engine::general_purpose::STANDARD};
use data_encoding::HEXLOWER;
use iroh::{PublicKey, SecretKey, Signature};
use std::{
    fs::{self, File, OpenOptions},
    io::{Read, Write},
    os::{
        fd::AsRawFd,
        unix::fs::{DirBuilderExt, MetadataExt, OpenOptionsExt},
    },
    path::Path,
};

pub struct Identity {
    pub(crate) secret: SecretKey,
    _lock: File,
}
impl Identity {
    pub fn load(root: &Path) -> Result<Self> {
        match fs::DirBuilder::new()
            .recursive(true)
            .mode(0o700)
            .create(root)
        {
            Ok(()) => (),
            Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => (),
            Err(_) => return Err(Error("state_io")),
        }
        let dir = fs::symlink_metadata(root).map_err(|_| Error("state_io"))?;
        if !dir.is_dir() || dir.mode() & 0o077 != 0 || dir.uid() != unsafe { libc::geteuid() } {
            return Err(Error("state_permissions"));
        }
        let lock = OpenOptions::new()
            .create(true)
            .truncate(false)
            .read(true)
            .write(true)
            .mode(0o600)
            .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(root.join("node.lock"))
            .map_err(|_| Error("state_io"))?;
        check_private(&lock)?;
        if unsafe { libc::flock(lock.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
            return Err(Error("state_locked"));
        }
        let path = root.join("node.secret");
        let secret = match OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(&path)
        {
            Ok(mut file) => {
                check_private(&file)?;
                let mut bytes = [0u8; 32];
                file.read_exact(&mut bytes)
                    .map_err(|_| Error("invalid_secret"))?;
                if file.read(&mut [0u8; 1]).map_err(|_| Error("state_io"))? != 0 {
                    return Err(Error("invalid_secret"));
                }
                SecretKey::from_bytes(&bytes)
            }
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
                let secret = SecretKey::generate();
                // Complete and sync a private temporary file before publishing. The
                // lifetime state lock serializes publication, including first startup.
                let mut file =
                    tempfile::NamedTempFile::new_in(root).map_err(|_| Error("state_io"))?;
                file.write_all(&secret.to_bytes())
                    .and_then(|_| file.as_file().sync_all())
                    .map_err(|_| Error("state_io"))?;
                file.persist(path).map_err(|_| Error("state_io"))?;
                File::open(root)
                    .and_then(|f| f.sync_all())
                    .map_err(|_| Error("state_io"))?;
                secret
            }
            Err(_) => return Err(Error("state_io")),
        };
        Ok(Self {
            secret,
            _lock: lock,
        })
    }
    pub fn id(&self) -> PublicKey {
        self.secret.public()
    }
    pub async fn bind(
        &self,
        config: crate::transport::Config,
    ) -> Result<crate::transport::Transport> {
        crate::transport::Transport::bind(self.secret.clone(), config).await
    }
    pub fn sign(&self, data: &str) -> Result<String> {
        let bytes = STANDARD.decode(data).map_err(|_| Error("invalid_base64"))?;
        Ok(HEXLOWER.encode(&self.secret.sign(&bytes).to_bytes()))
    }
    pub fn verify(id: &str, data: &str, signature: &str) -> Result<bool> {
        let bytes = STANDARD.decode(data).map_err(|_| Error("invalid_base64"))?;
        let valid = (|| {
            let key: PublicKey = id.parse().ok()?;
            let sig = HEXLOWER.decode(signature.as_bytes()).ok()?;
            let sig = Signature::try_from(sig.as_slice()).ok()?;
            Some(key.verify(&bytes, &sig).is_ok())
        })()
        .unwrap_or(false);
        Ok(valid)
    }
}
fn check_private(file: &File) -> Result<()> {
    let meta = file.metadata().map_err(|_| Error("state_io"))?;
    if !meta.is_file()
        || meta.mode() & 0o777 != 0o600
        || meta.nlink() != 1
        || meta.uid() != unsafe { libc::geteuid() }
    {
        return Err(Error("state_permissions"));
    }
    Ok(())
}
