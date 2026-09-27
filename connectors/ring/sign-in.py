"""Interactive sign-in on the uConsole. Passwords and tokens never enter chat."""
import fcntl,getpass,json,os,subprocess,sys
from pathlib import Path
app=Path(__file__).resolve().parent
config=Path.home()/'.config/uconsole-ring';config.mkdir(parents=True,exist_ok=True,mode=0o700)
os.chmod(config,0o700)
lock=(config/'connection.lock').open('a')
try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
except BlockingIOError:raise SystemExit('A Ring connection is already running. Stop that view before signing in.')
if not sys.stdin.isatty():raise SystemExit('Run this sign-in directly in a uConsole terminal.')
node=json.loads((app/'runtime.json').read_text())['node']
print('Connect Ring to uConsole Camera\n')
print('This community connector signs in to Ring. Your password is not saved.\n')
process=subprocess.Popen([node,str(app/'client.mjs'),'auth'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
try:
    while line:=process.stdout.readline(10000):
        event=json.loads(line)
        if event.get('prompt')=='credentials':
            data={'email':input('Ring email: ').strip(),'password':getpass.getpass('Ring password (hidden): ')}
            process.stdin.write(json.dumps(data)+'\n');process.stdin.flush();del data
            print('Contacting Ring…',flush=True)
        elif event.get('prompt')=='verification':
            if event.get('retry'):print('That code was not accepted; try the latest code.')
            code=getpass.getpass('Ring verification code (hidden): ').strip()
            process.stdin.write(json.dumps({'code':code})+'\n');process.stdin.flush();del code
        elif event.get('status') in ('connected','already_connected'):
            print('\nRing connected. You can return to the chat.',flush=True)
        elif event.get('status')=='failed':print(event['message'])
    if process.wait(timeout=5)!=0:print('Sign-in did not finish. Check your details and internet, then try again.')
except (KeyboardInterrupt,EOFError):print('\nSign-in cancelled.')
finally:
    if process.poll() is None:
        process.terminate()
        try:process.wait(timeout=3)
        except subprocess.TimeoutExpired:process.kill();process.wait()
input('\nPress Enter to close. ')
