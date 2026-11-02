/** Native Pi1.4.0 gate probe; provider execution is an explicit counter fixture. */
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,writeFile} from 'node:fs/promises';
import {join,resolve} from 'node:path';
import {tmpdir} from 'node:os';
import {pathToFileURL} from 'node:url';
const [nativeRoot,repo,output,mode]=process.argv.slice(2);
const temp=await mkdtemp(join(tmpdir(),'xsm-pi-owned-gate-'));
for(const key of Object.keys(process.env))if(!['PATH','LANG','TMPDIR','XSM_OWNED_CONTROL_FD'].includes(key))delete process.env[key];
for(const name of ['home','pi','project'])await mkdir(join(temp,name));
Object.assign(process.env,{HOME:join(temp,'home'),PI_CODING_AGENT_DIR:join(temp,'pi'),XSM_HOME:join(temp,'state'),PYTHONDONTWRITEBYTECODE:'1'});
const sdk=await import(pathToFileURL(join(nativeRoot,'dist/index.js')));
assert.equal(sdk.VERSION,'1.4.0');
await writeFile(join(temp,'pi/models.json'),JSON.stringify({providers:{'xsm-fixture':{baseUrl:'http://127.0.0.1:9',api:'openai-completions',apiKey:'explicit-no-network-fixture',models:[{id:'fixture',name:'fixture',reasoning:false,input:['text'],contextWindow:32000,maxTokens:1000,cost:{input:0,output:0,cacheRead:0,cacheWrite:0}}]}}}));
const settings=sdk.SettingsManager.inMemory({compaction:{enabled:false},retry:{enabled:false},defaultProvider:'xsm-fixture',defaultModel:'fixture'});
const loader=new sdk.DefaultResourceLoader({cwd:join(temp,'project'),agentDir:join(temp,'pi'),settingsManager:settings,additionalExtensionPaths:[join(repo,'integrations/pi/xsm.mjs')],noSkills:true,noPromptTemplates:true,noThemes:true,noContextFiles:true});
let session;const report={mode,root:temp,modelCalls:0,scope:'actual pinned native SDK and private socket; model invocation replaced by explicit counter fixture'};
try{
 await loader.reload();
 const loaded=await sdk.createAgentSession({cwd:join(temp,'project'),agentDir:join(temp,'pi'),settingsManager:settings,sessionManager:sdk.SessionManager.inMemory(),resourceLoader:loader});
 session=loaded.session;
 assert.equal(loaded.extensionsResult.errors.length,0);
 await session.bindExtensions({mode:'rpc',uiContext:{notify(){},setStatus(){}}});
 session.agent.streamFunction=(_model,_context,options)=>{report.signalAborted=options?.signal?.aborted;report.modelCalls++;throw new Error('explicit provider counter fixture');};
 report.nativeID=session.sessionManager.getSessionId();
 await session.prompt('Explicit native pre-model gate test.');
 assert.equal(report.modelCalls,mode==='accept'?1:0);
 report.passed=true;
} catch(error){report.passed=false;report.failure=error.message;}
finally{
 if(session){await session.extensionRunner.emit({type:'session_shutdown',reason:'quit'});session.dispose();}
 await writeFile(output,JSON.stringify(report,null,2)+'\n');
}
console.log(JSON.stringify(report));
process.exitCode=report.passed?0:1;
