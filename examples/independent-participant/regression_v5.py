"""Run our unchanged v3 contract scenarios using the new own v5 participant.

All argv remain explicit operator choices. No prior result or xsm SDK is loaded.
"""
import verify_v3
from participant_v5 import Peer

if __name__=='__main__':
    verify_v3.Peer=Peer
    raise SystemExit(verify_v3.main())
