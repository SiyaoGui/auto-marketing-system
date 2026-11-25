from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .content import eligible_assets
from .core import safe_path, write_json


def ffmpeg_path(cfg):
    explicit = cfg['media'].get('ffmpeg') or os.environ.get('IMAGEIO_FFMPEG_EXE') or shutil.which('ffmpeg')
    if explicit:
        if not Path(explicit).is_file() and not shutil.which(explicit):
            raise RuntimeError('Configured FFmpeg executable not found')
        return explicit
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        # Reuse an already installed binary on this workstation without changing its parent app.
        existing = Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs/Stremio/ffmpeg.exe'
        if existing.is_file():
            return str(existing)
        raise RuntimeError('FFmpeg missing. Run scripts/setup.ps1 with internet access or set media.ffmpeg')


def font_path(cfg):
    value = cfg['media'].get('font')
    candidates = [value, 'C:/Windows/Fonts/msyh.ttc', 'C:/Windows/Fonts/arial.ttf',
                  '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']
    for p in candidates:
        if p and Path(p).is_file():
            return str(p)
    raise RuntimeError('Set media.font to a font supporting the brand language')


def lines(text, font, width):
    result = []
    for paragraph in text.split('\n'):
        line = ''
        tokens = list(paragraph) if re.search('[\u3400-\u9fff]', paragraph) else paragraph.split(' ')
        sep = '' if re.search('[\u3400-\u9fff]', paragraph) else ' '
        for token in tokens:
            proposed = (line + sep + token).strip()
            if font.getlength(proposed) > width and line:
                result.append(line)
                line = token
            else:
                line = proposed
        result.append(line)
    return result


def card(root, cfg, brand, scene, index, total, output, asset=None, overlay=False):
    w, h = cfg['media']['width'], cfg['media']['height']
    scale = w / 1080
    im = Image.new('RGBA', (w, h), (16, 26, 36, 0 if overlay else 255))
    if asset and asset.suffix.lower() in ('.jpg', '.jpeg', '.png', '.webp'):
        with Image.open(asset) as original:
            im = ImageOps.fit(original.convert('RGB'), (w, h)).convert('RGBA')
        overlay = True
    dr = ImageDraw.Draw(im)
    if overlay:
        shade = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        sd = ImageDraw.Draw(shade)
        for y in range(h):
            alpha = int(80 + 130 * abs(y / h - 0.48) * 2)
            sd.line((0, y, w, y), fill=(8, 17, 24, min(alpha, 220)))
        im = Image.alpha_composite(im, shade)
        dr = ImageDraw.Draw(im)
    else:
        dr.ellipse((int(w*.4), int(h*.32), int(w*1.4), int(h*.9)), fill='#203E41')
        dr.ellipse((int(w*.68), int(h*.37), int(w*1.1), int(h*.63)), outline=brand['accent'], width=3)
        dr.line((70*scale, 450*scale, 800*scale, 450*scale), fill='#365958', width=2)
    fontfile = font_path(cfg)
    small = ImageFont.truetype(fontfile, int(30*scale))
    dr.text((80*scale, 205*scale), brand['name'][:32], font=small, fill=brand['accent'])
    size = int(96*scale)
    while size > 30*scale:
        titlefont = ImageFont.truetype(fontfile, int(size))
        wrapped = lines(scene['headline'], titlefont, 790*scale)
        if len(wrapped) <= 4 and all(titlefont.getlength(s) <= 790*scale for s in wrapped):
            break
        size -= 3
    if len(wrapped) > 4 or any(titlefont.getlength(s) > 790*scale for s in wrapped):
        raise ValueError('Headline does not fit the visual safe area')
    for j, text in enumerate(wrapped):
        dr.text((80*scale, (535 + j*(size/scale+17))*scale), text, font=titlefont, fill='white')
    bodyfont = ImageFont.truetype(fontfile, int(40*scale))
    body = lines(scene['narration'], bodyfont, 780*scale)
    if len(body) > 4 or any(bodyfont.getlength(s) > 780*scale for s in body):
        raise ValueError('Subtitle exceeds the safe text area; shorten narration')
    y = 1260*scale
    dr.rounded_rectangle((64*scale, y-25*scale, 900*scale, y+(len(body)*60+22)*scale), radius=int(20*scale), fill=(8,17,24,230))
    for j, text in enumerate(body):
        dr.text((88*scale, y+j*60*scale), text, font=bodyfont, fill='white')
    for j in range(total):
        x = (80+j*195)*scale
        dr.rounded_rectangle((x, 1640*scale, x+170*scale, 1647*scale), radius=3, fill=brand['accent'] if j <= index else '#526165')
    dr.text((80*scale, 1690*scale), 'DEMO / NOT FOR PUBLICATION' if brand.get('demo') else f'{index+1:02d} / {total:02d}', font=small, fill='#A3B6B4')
    im.save(output)


def storyboard(root, cfg, brand, script, folder):
    folder.mkdir(parents=True, exist_ok=True)
    assets = {a['id']: safe_path(root, a['path']) for a in eligible_assets(root, brand)}
    for i, scene in enumerate(script['scenes']):
        asset = assets.get(scene.get('asset_id'))
        card(root, cfg, brand, scene, i, len(script['scenes']), folder / f'card-{i}.png', asset=asset,
             overlay=bool(asset and asset.suffix.lower() in ('.mp4', '.mov')))
    previews = []
    for i in range(len(script['scenes'])):
        with Image.open(folder / f'card-{i}.png') as im:
            previews.append(im.convert('RGB').resize((270, 480)))
    sheet = Image.new('RGB', (270*len(previews), 480), '#101A24')
    for i, im in enumerate(previews):
        sheet.paste(im, (i*270, 0))
    sheet.save(folder / 'storyboard.jpg', quality=92)
    write_json(folder / 'script.json', script)
    return assets


def speak(root, cfg, brand, text, wav):
    tts = cfg['tts']
    if tts['engine'] == 'windows':
        spec = wav.with_suffix('.speech.json')
        write_json(spec, {'text': text, 'output': str(wav.resolve()), 'voice': tts.get('voice'), 'language': brand['language']})
        cmd = ['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
               '-File', str(root / 'scripts/speak.ps1'), '-InputJson', str(spec.resolve())]
        r = subprocess.run(cmd, capture_output=True, timeout=120)
        if r.returncode:
            raise RuntimeError('Windows voice generation failed; install the brand language voice or configure Piper')
    elif tts['engine'] == 'piper':
        if not tts.get('voice_license_confirmed'):
            raise ValueError('Confirm the Piper voice model permits your commercial use')
        model = safe_path(root, tts['piper_model'])
        cmd = [tts['piper_command'], '--model', str(model), '--output_file', str(wav)]
        r = subprocess.run(cmd, input=text.encode('utf-8'), capture_output=True, timeout=180)
        if r.returncode:
            raise RuntimeError('Piper speech generation failed')
    else:
        raise ValueError('Configure tts.engine as windows or piper')
    with wave.open(str(wav), 'rb') as reader:
        seconds = reader.getnframes() / reader.getframerate()
    if not 0.3 <= seconds <= 25:
        raise ValueError('Unexpected speech duration')
    return seconds


def run_ffmpeg(exe, args, cwd):
    result = subprocess.run([exe, '-hide_banner', '-loglevel', 'error', '-y', *args], cwd=cwd, capture_output=True, timeout=600)
    if result.returncode:
        # Encoder output contains only local paths/parameters, not platform credentials.
        (cwd / 'render-error.log').write_bytes(result.stderr[-6000:])
        raise RuntimeError('FFmpeg failed; inspect render-error.log')


def srt_time(seconds):
    ms = int(round(seconds*1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f'{h:02}:{m:02}:{s:02},{ms:03}'


def render(root, cfg, brand, script, folder):
    assets = storyboard(root, cfg, brand, script, folder)
    exe = ffmpeg_path(cfg)
    w, h, fps = (cfg['media'][k] for k in ('width', 'height', 'fps'))
    durations, subtitles, total = [], [], 0
    for i, scene in enumerate(script['scenes']):
        duration = max(3.0, speak(root, cfg, brand, scene['narration'], folder / f'voice-{i}.wav') + .4)
        durations.append(duration)
        subtitles.append(f'{i+1}\n{srt_time(total)} --> {srt_time(total+duration)}\n{scene["narration"]}\n')
        total += duration
        asset = assets.get(scene.get('asset_id'))
        if asset and asset.suffix.lower() in ('.mp4', '.mov'):
            args = ['-stream_loop', '-1', '-i', str(asset), '-loop', '1', '-i', f'card-{i}.png', '-i', f'voice-{i}.wav',
                    '-filter_complex', f'[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1[bg];[bg][1:v]overlay=0:0[v];[2:a]apad[a]',
                    '-map', '[v]', '-map', '[a]']
        else:
            # Ken Burns motion; output sizes and captions remain in safe areas after the subtle zoom.
            frames = max(1, round(duration*fps))
            args = ['-loop', '1', '-i', f'card-{i}.png', '-i', f'voice-{i}.wav',
                    '-vf', f"zoompan=z='1+0.025*on/{frames}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d=1:s={w}x{h}:fps={fps},setsar=1",
                    '-af', 'apad', '-map', '0:v', '-map', '1:a']
        args += ['-t', str(duration), '-r', str(fps), '-c:v', 'libx264', '-preset', 'fast', '-crf', '20',
                 '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '160k', '-ar', '48000', '-ac', '2', '-movflags', '+faststart', f'scene-{i}.mp4']
        run_ffmpeg(exe, args, folder)
    if not cfg['media']['min_seconds'] <= total <= cfg['media']['max_seconds']:
        raise ValueError(f'Video duration {total:.1f}s outside configured range')
    (folder / 'concat.txt').write_text('\n'.join(f"file 'scene-{i}.mp4'" for i in range(len(durations))), encoding='utf-8')
    run_ffmpeg(exe, ['-f', 'concat', '-safe', '0', '-i', 'concat.txt', '-c', 'copy', '-movflags', '+faststart', 'video.mp4'], folder)
    # Decode every frame/audio packet. Do not accept a file merely because FFmpeg returned an output path.
    run_ffmpeg(exe, ['-xerror', '-i', 'video.mp4', '-f', 'null', '-'], folder)
    (folder / 'captions.srt').write_text('\n'.join(subtitles), encoding='utf-8')
    shutil.copyfile(folder / 'card-0.png', folder / 'cover.png')
    quality = {'passed': True, 'duration_seconds': round(total, 3), 'width': w, 'height': h,
               'fps': fps, 'codec': 'h264', 'audio': 'aac', 'captions': 'scene-level burned captions and SRT',
               'full_decode_passed': True, 'editorial_quality': 'requires brand sample evaluation',
               'demo': script.get('demo', False)}
    write_json(folder / 'quality.json', quality)
    return quality
