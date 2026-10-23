"""Assemble a captioned walkthrough from actual browser screenshots.

Optional dependencies: pip install pillow imageio-ffmpeg
Capture files are documentation evidence; no generated factory imagery is used.
"""
from pathlib import Path
import subprocess
from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg

ROOT=Path(__file__).resolve().parents[1]
MEDIA=ROOT/'docs'/'media'
W,H,FPS=1280,840,12


def font(size):
    for path in ['C:/Windows/Fonts/segoeui.ttf','/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']:
        if Path(path).exists(): return ImageFont.truetype(path,size)
    return ImageFont.load_default()


def frame(file,title,caption):
    image=Image.new('RGB',(W,H),'#f5f4ef');draw=ImageDraw.Draw(image)
    draw.rectangle((0,0,W,76),fill='#202c2a')
    draw.text((26,19),title,font=font(25),fill='#f1f1e9')
    shot=Image.open(MEDIA/file).convert('RGB')
    image.paste(shot,((W-shot.width)//2,78))
    draw.rectangle((0,796,W,H),fill='#e6e9de')
    draw.text((24,807),caption,font=font(16),fill='#263d30')
    return image


def card(title,lines):
    im=Image.new('RGB',(W,H),'#202c2a');d=ImageDraw.Draw(im)
    d.rectangle((68,150,77,215),fill='#b89658')
    d.text((105,150),'FABWATCH',font=font(52),fill='#f5f4ef')
    d.text((105,240),title,font=font(30),fill='#d7dfce')
    for i,line in enumerate(lines): d.text((105,340+i*55),line,font=font(21),fill='#b9c5b7')
    d.text((105,740),'Independent portfolio | Actual local application captures | No factory connection',font=font(17),fill='#b89658')
    return im


def main():
    shots=[(card('Semiconductor manufacturing quality intelligence',[
        '1,567 real process records / 590 anonymous signals',
        'Python + SQL + statistical ML + engineering investigations',
        'Working ingestion, historical replay, and auditable human review']),4)]
    shots.append((frame('00-empty.png','01 / Operations and historical replay','Observed outcomes are separate from risk estimates; synthetic outcome delay = 10 records.'),3))
    for i in range(1,14):
        shots.append((frame(f'replay-{i:02d}.png','02 / Chronological scoring in the running application',
                            f'Actual replay capture {i}/13 | Frozen model; no retraining or fabricated production feed.'),1))
    for file,title,caption,seconds in [
        ('operations.png','03 / Complete held-out replay','314 entities / 304 revealed outcomes / 10 pending / 3 quality holds.',5),
        ('investigations.png','04 / Engineering investigation queue','8 cases: 3 data quality holds + 5 reference excursions. Excursions are not proven failures.',6),
        ('handoff.png','05 / Assign ownership and preserve evidence','Actual saved demo note and status change; accountable follow-up recorded in the audit trail.',6),
        ('quality.png','06 / Data contracts and process monitoring','Signal completeness + exploratory EWMA. No physical root causes or specification limits invented.',6),
        ('model-evidence.png','07 / Inspect model evidence and limitations','The original chronological model is weak; risk alerts remain disabled under its selected policy.',7),
        ('entity-evidence.png','08 / Inspect an entity and its audit history','Reference deviations support investigation; they do not establish causal attribution.',6)]:
        shots.append((frame(file,title,caption),seconds))
    shots.append((card('Reproducible evidence, accountable decisions',[
        '29 automated tests / 314 entity-evidence checks',
        'Source and model fingerprints / SQL KPIs / reporting exports',
        'No demonstrated production yield improvement; future/site validation required']),4))
    cmd=[imageio_ffmpeg.get_ffmpeg_exe(),'-y','-f','rawvideo','-vcodec','rawvideo','-s',f'{W}x{H}',
         '-pix_fmt','rgb24','-r',str(FPS),'-i','-','-an','-vcodec','libx264','-preset','fast','-crf','22',
         '-pix_fmt','yuv420p','-movflags','+faststart',str(MEDIA/'fabwatch-demo.mp4')]
    process=subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    for image,duration in shots:
        raw=image.tobytes()
        for _ in range(duration*FPS): process.stdin.write(raw)
    process.stdin.close()
    if process.wait()!=0: raise RuntimeError('Video encoding failed')
    frames=[]
    for i in range(1,14):
        image=Image.open(MEDIA/f'replay-{i:02d}.png').convert('RGB')
        image.thumbnail((960,540));frames.append(image.convert('P',palette=Image.Palette.ADAPTIVE,colors=96))
    frames[0].save(MEDIA/'replay.gif',save_all=True,append_images=frames[1:],duration=[650]*12+[2400],loop=0,optimize=True)
    print({'video_seconds':sum(duration for _,duration in shots),'video_bytes':(MEDIA/'fabwatch-demo.mp4').stat().st_size,
           'gif_bytes':(MEDIA/'replay.gif').stat().st_size})


if __name__=='__main__':main()
