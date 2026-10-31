#!/usr/bin/env python3
"""One explicitly invoked, bounded fresh-session stream check; no recordings.

Credentials remain local. Output contains only stages, counts and allowlisted
codec names. It does not install packages or modify Home Assistant/services.
"""
import argparse
import asyncio
import contextlib
import getpass
import importlib
import json
from pathlib import Path
import shutil
import sys
import types

ROOT=Path(__file__).resolve().parents[1]
p=types.ModuleType('virtavo_stream_check_engine')
p.__path__=[str(ROOT/'custom_components/virtavo/engine')]
sys.modules[p.__name__]=p
account=importlib.import_module(p.__name__+'.account')
discovery=importlib.import_module(p.__name__+'.discovery')
service=importlib.import_module(p.__name__+'.service')
receiver=importlib.import_module(p.__name__+'.receiver')
net=importlib.import_module(p.__name__+'.net_auth')


def _open(config,index,on_login=None):
    connection=None
    try:
        connection=account.open_account(config)
        if on_login is not None:on_login()
        inventory=discovery.discover_account_devices(connection)
        if not 0<=index<len(inventory.devices):
            raise ValueError('Device index unavailable')
        device=inventory.devices[index]
        group=dict(inventory.device_owner_types)[device.device_id]
        identity=service.parse_device_identity(device.name,connection.session.canonical_username,group)
        identity.play_username
        return service.SessionContext(connection,device,group,identity)
    except BaseException:
        if connection is not None:connection.close()
        raise


async def _open_owned(config,index,on_login=None):
    task=asyncio.create_task(asyncio.to_thread(_open,config,index,on_login))
    try:return await asyncio.shield(task)
    except asyncio.CancelledError:
        def close_late(future):
            try:context=future.result()
            except BaseException:return
            context.close()
        task.add_done_callback(close_late)
        raise


def _codec_counts(raw):
    data=json.loads(raw)
    if not isinstance(data,dict) or not isinstance(data.get('streams',[]),list):
        raise ValueError('Decoder summary malformed')
    result={'video_frames':0,'audio_frames':0,'video_codec':None,'audio_codec':None}
    for item in data.get('streams',[]):
        if not isinstance(item,dict):raise ValueError('Decoder stream malformed')
        name=item.get('codec_name');kind=item.get('codec_type')
        count=item.get('nb_read_frames','0')
        try:count=int(count)
        except (ValueError,TypeError):count=0
        if not 0<=count<=1000000:count=0
        if kind=='video' and name=='hevc':
            result['video_codec']='hevc';result['video_frames']+=count
        if kind=='audio' and name=='aac':
            result['audio_codec']='aac';result['audio_frames']+=count
    return result


async def _reap(process):
    if process is None:return
    if process.stdin is not None:process.stdin.close()
    if process.returncode is None:
        with contextlib.suppress(ProcessLookupError):process.terminate()
    try:await asyncio.wait_for(process.wait(),3)
    except asyncio.TimeoutError:
        with contextlib.suppress(ProcessLookupError):process.kill()
        await process.wait()


async def probe(config,*,seconds=10,audio=True,index=0,on_login=None):
    if type(seconds) is not int or not 1<=seconds<=15 or type(audio) is not bool:
        raise ValueError('Bounded duration and explicit audio setting required')
    if type(index) is not int or index<0:raise ValueError('Nonnegative device index required')
    result={'diagnostic_version':1,'scope':'fresh_NET_stream','camera_started':False,
            'recording_saved':False,'audio_requested':audio,'sample_seconds':seconds,
            'stage':'preflight','status':'not_completed'}
    context=None;transport=None;process=None;exit_code=4
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        result.update(status='missing_ffmpeg_or_ffprobe');return result,2
    try:
        receiver.country_mode(config.country)
        result['stage']='fresh_account_and_device'
        context=await _open_owned(config,index,on_login)
        transport=receiver.RelayReceiver(context,context.device.device_id,config.country)
        code=receiver.wire.des_initial_code(context.identity.play_username,context.device.device_id)
        result['shared_device']=context.identity.is_shared
        result['stage']='decoder_start'
        process=await asyncio.create_subprocess_exec('ffprobe','-v','quiet','-count_frames',
                    '-show_entries','stream=codec_name,codec_type,nb_read_frames','-of','json',
                    '-i','pipe:0',stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL)
        async def source(video,audio_sink):
            await transport.open()
            result['camera_started']=True
            result['stage']='streaming_sample'
            task=asyncio.create_task(transport.pump(video,audio_sink))
            try:
                done,_=await asyncio.wait((task,),timeout=seconds)
                if done:task.result()
            finally:
                task.cancel();await asyncio.gather(task,return_exceptions=True)
                await transport.close()
        await receiver.run_media_pipeline(source,code,process.stdin,audio=audio)
        result['stage']='decode_summary'
        process.stdin.close()
        async def read_summary():
            chunks=[];size=0
            while chunk:=await process.stdout.read(4096):
                size+=len(chunk)
                if size>65536:raise ValueError('Decoder summary exceeded bound')
                chunks.append(chunk)
            status=await process.wait()
            if status:raise ValueError('Decoder summary unavailable')
            return b''.join(chunks)
        raw=await asyncio.wait_for(read_summary(),10)
        result.update(_codec_counts(raw))
        success=result['video_frames']>0 and (not audio or result['audio_frames']>0)
        result.update(status='verified' if success else 'decode_not_verified',stage='complete')
        exit_code=0 if success else 3
    except net.AuthenticationError:
        result['status']='authentication_rejected'
    except (TimeoutError,asyncio.TimeoutError):
        result['status']='timeout'
    except (OSError,ConnectionError):
        result['status']='connection_or_process_error'
    except (ValueError,RuntimeError):
        result['status']='protocol_or_decode_error'
    finally:
        cleanup_ok=True
        # Every owned resource gets its cleanup attempt, including if an
        # earlier close raises or cancellation arrives during transport close.
        try:
            if transport is not None:
                result['receiver_stage']=transport.stage
                result['packets']=dict(transport.stats)
                try:await transport.close()
                except Exception:cleanup_ok=False
        finally:
            try:
                if context is not None:
                    try:context.close()
                    except Exception:cleanup_ok=False
            finally:
                try:await _reap(process)
                except Exception:cleanup_ok=False
        if not cleanup_ok:
            result['status']='cleanup_error'
            exit_code=4
    return result,exit_code



async def bounded_probe(config,**kwargs):
    try:
        return await asyncio.wait_for(probe(config,**kwargs),75)
    except TimeoutError:
        return {'diagnostic_version':1,'scope':'fresh_NET_stream','status':'overall_timeout',
                'recording_saved':False},4


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--region',choices=('fr','ca','sg','sp','sh','ru'),default='fr')
    parser.add_argument('--country',default='IT')
    parser.add_argument('--seconds',type=int,choices=range(1,16),default=10)
    parser.add_argument('--device-index',type=int,default=0,help='Zero-based discovery index, default first device')
    parser.add_argument('--no-audio',action='store_true')
    args=parser.parse_args()
    email=input('Email IPC360 Home: ').strip()
    password=getpass.getpass('Password IPC360 Home (non visualizzata): ')
    try:
        config=account.AccountConfig(email,password,country=args.country,server_code=args.region)
        result,status=asyncio.run(bounded_probe(config,seconds=args.seconds,audio=not args.no_audio,index=args.device_index,
                    on_login=lambda:print('Login corretto.',file=sys.stderr,flush=True)))
    finally:password=None;email=None
    print(json.dumps(result,sort_keys=True))
    return status

if __name__=='__main__':
    try:sys.exit(main())
    except (KeyboardInterrupt,EOFError):
        print(json.dumps({'diagnostic_version':1,'status':'cancelled','recording_saved':False}));sys.exit(130)
    except Exception:
        # Deliberately do not serialize exception messages or print tracebacks.
        print(json.dumps({'diagnostic_version':1,'status':'unexpected_error','recording_saved':False}));sys.exit(5)
