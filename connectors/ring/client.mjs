import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {createInterface} from 'node:readline';
import {RingApi} from 'ring-client-api';
import {RingRestClient} from 'ring-client-api/rest-client';
import {useLogger} from 'ring-client-api/util';

// The library may attach request details to errors. Never write them to logs.
useLogger({logInfo(){},logError(){}});
const config=path.join(os.homedir(),'.config/uconsole-ring');
const authFile=path.join(config,'auth.json');
const mode=process.argv[2];
let api,session,stopping=false;
function saveAuth(auth){
  fs.mkdirSync(config,{recursive:true,mode:0o700});
  const tmp=authFile+'.'+process.pid+'.tmp';
  fs.writeFileSync(tmp,JSON.stringify(auth),{mode:0o600,flag:'wx'});
  fs.renameSync(tmp,authFile);
}
function report(data){process.stdout.write(JSON.stringify(data)+'\n');}
function finish(code=0){
  if(stopping)return;
  stopping=true;
  try{session?.stop();api?.disconnect();}catch{}
  setTimeout(()=>process.exit(code),100);
}
process.on('SIGTERM',()=>finish());process.on('SIGINT',()=>finish());
process.stdout.on('error',()=>finish(1));
process.on('uncaughtException',()=>{process.stderr.write('Ring connection failed.\n');finish(1);});
process.on('unhandledRejection',()=>{process.stderr.write('Ring connection failed.\n');finish(1);});

async function connect(auth){
  api=new RingApi({...auth,controlCenterDisplayName:'uConsole Camera',ffmpegPath:'/usr/bin/ffmpeg',avoidSnapshotBatteryDrain:true});
  api.onRefreshTokenUpdated.subscribe(({newRefreshToken})=>saveAuth({...auth,refreshToken:newRefreshToken}));
  return api;
}
async function authenticate(){
  if(fs.existsSync(authFile)){report({status:'already_connected'});return finish();}
  const lines=createInterface({input:process.stdin,crlfDelay:Infinity})[Symbol.asyncIterator]();
  async function answer(){const next=await lines.next();if(next.done)throw Error('Input closed');return JSON.parse(next.value);}
  report({prompt:'credentials'});
  const credentials=await answer();
  if(typeof credentials.email!=='string'||typeof credentials.password!=='string')throw Error('Missing sign-in');
  const systemId=randomUUID();
  const rest=new RingRestClient({...credentials,systemId,controlCenterDisplayName:'uConsole Camera'});
  let response;
  try{response=await rest.getCurrentAuth();}
  catch{
    if(!rest.promptFor2fa){report({status:'failed',message:'Ring sign-in failed. Check your email, password, and internet connection.'});return finish(1);}
    for(let attempt=0;attempt<3&&!response;attempt++){
      report({prompt:'verification',retry:attempt>0});
      const {code}=await answer();
      try{response=await rest.getAuth(String(code));}catch{}
    }
  }
  if(!response){report({status:'failed',message:'Ring did not accept the verification code. Run Connect Ring again.'});return finish(1);}
  saveAuth({refreshToken:response.refresh_token,systemId});
  rest.clearTimeouts();
  report({status:'connected'});finish();
}
async function cameras(){
  if(!fs.existsSync(authFile))throw Error('SIGN_IN_REQUIRED');
  const auth=JSON.parse(fs.readFileSync(authFile,'utf8'));
  await connect(auth);
  const list=await api.getCameras();
  const discovered=list.filter(c=>['Back','Side','Front Door'].includes(c.name));
  const metadata=discovered.map(c=>({id:String(c.id),name:c.name,model:c.model,offline:c.isOffline,battery:c.batteryLevel}));
  // This file contains camera identifiers, never credentials, and is user-private.
  fs.writeFileSync(path.join(config,'cameras.json'),JSON.stringify(metadata),{mode:0o600});
  if(mode==='list'){
    await new Promise(resolve=>setTimeout(resolve,3000));
    report({cameras:metadata.map(({id,...rest})=>rest)});finish();return;
  }
  const selected=discovered.filter(c=>c.name===process.argv[3]);
  if(selected.length!==1)throw Error('CAMERA_NOT_FOUND');
  const camera=selected[0];
  if(camera.isOffline)throw Error('CAMERA_OFFLINE');
  const duration=Number(process.argv[4]||60);
  if(!Number.isInteger(duration)||duration<5||duration>300)throw Error('INVALID_DURATION');
  session=await camera.startLiveCall();
  session.onCallEnded.subscribe(()=>finish());
  setTimeout(()=>finish(),duration*1000);
  await session.startTranscoding({
    input:['-threads','1'],audio:['-an'],
    video:['-vf','fps=8,scale=640:-2','-c:v','mjpeg','-q:v','6','-threads','1'],
    output:['-an','-f','mpjpeg','-boundary_tag','frame','pipe:1'],
    stdoutCallback:buffer=>{if(!stopping)process.stdout.write(buffer);},
  });
}
setTimeout(()=>{process.stderr.write('Ring connection timed out.\n');finish(1);},mode==='auth'?600000:330000).unref();
if(!['auth','list','stream'].includes(mode)){process.stderr.write('Choose auth, list, or stream.\n');process.exit(1);}
try{await(mode==='auth'?authenticate():cameras());}
catch(error){
  const messages={SIGN_IN_REQUIRED:'Connect Ring first.',CAMERA_NOT_FOUND:'That Ring camera name was not found uniquely.',CAMERA_OFFLINE:'This camera is offline in Ring.',INVALID_DURATION:'Choose a live session of 5 to 300 seconds.'};
  process.stderr.write((messages[error.message]||'Ring connection failed. Check sign-in and internet access.')+'\n');finish(1);
}
