"""Offline transcription, no external audio transmission and no API charges."""
import argparse, json, hashlib, time, wave
import numpy as np
from pathlib import Path
from faster_whisper import WhisperModel

if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--model',required=True);p.add_argument('--audio',required=True);p.add_argument('--output',required=True)
    p.add_argument('--chunk-seconds',type=int,default=0)
    args=p.parse_args();source=Path(args.audio);out=Path(args.output)
    model=WhisperModel(args.model,device='cpu',compute_type='int8',cpu_threads=4,local_files_only=True)
    start=time.monotonic()
    with wave.open(str(source),'rb') as wav:
        if (wav.getframerate(),wav.getnchannels(),wav.getsampwidth()) != (16000,1,2):
            raise ValueError('Expected 16kHz mono signed PCM16 WAV')
        waveform=np.frombuffer(wav.readframes(wav.getnframes()),dtype='<i2').astype(np.float32)/32768.0
    rows=[]
    step=args.chunk_seconds*16000 if args.chunk_seconds else len(waveform)
    for offset in range(0,len(waveform),step):
        seconds=offset/16000
        segments,info=model.transcribe(waveform[offset:offset+step],language='zh',beam_size=5,vad_filter=not bool(args.chunk_seconds),condition_on_previous_text=False,word_timestamps=True)
        for s in segments:
            rows.append({'start':seconds+s.start,'end':seconds+s.end,'text':s.text.strip(),'avg_logprob':s.avg_logprob,
                         'no_speech_prob':s.no_speech_prob,'words':[{'start':seconds+w.start,'end':seconds+w.end,'word':w.word,'probability':w.probability} for w in (s.words or [])]})
            print(f'segment {len(rows)}: {seconds+s.start:.2f}-{seconds+s.end:.2f}',flush=True)
    result={'engine':'faster-whisper','model':'base','local_only':True,'api_cost_usd':0,
            'review_status':'unreviewed_machine_transcript','audio_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
            'language':info.language,'duration':len(waveform)/16000,'chunk_seconds':args.chunk_seconds,
            'elapsed_seconds':round(time.monotonic()-start,2),'segments':rows}
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'segments':len(rows),'seconds':result['elapsed_seconds'],'output':str(out)}))
