"""Render fictional demo media; never capture the desktop or read settings.

Development only: Pillow, plus FFmpeg for the optional --video output.
"""
import argparse
from pathlib import Path
import shutil
import subprocess
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
WIDTH, HEIGHT, FPS = 960, 540, 6
BG, PANEL, TEXT, MUTED = '#0B1220', '#152238', '#F1F5FC', '#9BB0CC'
CYAN, GREEN, AMBER, RED = '#41D9EF', '#68E0B0', '#FFCC70', '#FF767E'


def font(size, bold=False):
    names = ([r'C:\Windows\Fonts\segoeuib.ttf', '/System/Library/Fonts/Supplemental/Arial Bold.ttf', 'DejaVuSans-Bold.ttf']
             if bold else [r'C:\Windows\Fonts\segoeui.ttf', '/System/Library/Fonts/Supplemental/Arial.ttf', 'DejaVuSans.ttf'])
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


def text(draw, xy, value, size=20, color=TEXT, bold=False):
    draw.text(xy, value, font=font(size, bold), fill=color)


def pill(draw, box, label, accent=CYAN):
    draw.rounded_rectangle(box, radius=13, fill=PANEL, outline=accent, width=1)
    text(draw, (box[0]+15, box[1]+8), label, 16, accent, True)


def shield(draw, x, y, scale=1, color=CYAN):
    points = [(x,y), (x+35*scale,y-12*scale), (x+70*scale,y),
              (x+66*scale,y+45*scale), (x+35*scale,y+72*scale), (x+4*scale,y+45*scale)]
    draw.polygon(points, fill=PANEL, outline=color, width=3)
    draw.line([(x+19*scale,y+28*scale),(x+31*scale,y+40*scale),(x+52*scale,y+14*scale)], fill=color, width=4)


def header(english=False):
    image = Image.new('RGB', (WIDTH, 340), BG)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0,0,WIDTH,5), fill=CYAN)
    shield(draw, 748, 106, 1.5)
    text(draw, (48,40), 'LAPTOP GUARD', 48, TEXT, True)
    text(draw, (50,113), 'Local alarm. Activity recorded.' if english else 'Alarma local. Actividad registrada.', 27, CYAN)
    text(draw, (50,151), 'Your videos stay on your computer.' if english else 'Tus videos se quedan en tu computador.', 23, MUTED)
    pill(draw, (50,220,245,262), 'WINDOWS + macOS')
    pill(draw, (264,220,467,262), 'NO PYTHON REQUIRED' if english else 'SIN INSTALAR PYTHON', GREEN)
    pill(draw, (486,220,674,262), 'v1.1.0 PRE-RELEASE' if english else 'v1.1.0 PRELIMINAR', AMBER)
    text(draw, (50,292), 'ALERTS  /  LOCAL LOGS  /  3 ROTATING CLIPS' if english else 'ALERTA  /  REGISTRO LOCAL  /  3 VIDEOS ROTATIVOS', 16, MUTED, True)
    return image


STAGES = [('Configura', CYAN), ('Activa', CYAN), ('Detecta', RED), ('Registra', AMBER), ('Desactiva', GREEN)]
ENGLISH = {
    'Configura': 'Configure', 'Activa': 'Arm', 'Detecta': 'Detect',
    'Registra': 'Log', 'Desactiva': 'Disarm',
    'DEMO ILUSTRADA · DATOS FICTICIOS': 'ILLUSTRATED DEMO · FICTIONAL DATA',
    'Tu contacto y': 'Your contact and', 'tu combinación.': 'key combination.',
    'Actívalo cuando': 'Arm the guard', 'lo necesites.': 'when you need it.',
    'Un toque inicia': 'One touch starts', 'la alerta local.': 'the local alarm.',
    'Historial continuo.': 'Continuous history.', 'Tres clips rotativos.': 'Three rotating clips.',
    'Recupera el control': 'Regain control with', 'con tu combinación.': 'your combination.',
    'Contacto de demostración': 'Demo contact', 'TU NÚMERO AQUÍ': 'YOUR NUMBER HERE',
    'Combinación de ejemplo': 'Example key combination',
    'Al guardar, la protección se activa.': 'Saving arms the guard.',
    'PROTECCIÓN ACTIVA': 'GUARD ARMED',
    'También: activación automática a los 15 min*': 'Also: automatic arming after 15 idle minutes*',
    '*Automático: Windows': '*Automatic mode: Windows',
    'Aviso ficticio:': 'Fictional warning:', 'no borra archivos.': 'no files are deleted.',
    'logs / guard.jsonl  ·  historial': 'logs / guard.jsonl  ·  history',
    'El siguiente clip reemplaza al más antiguo.': 'The next clip replaces the oldest one.',
    'Alarma detenida': 'Alarm stopped',
    'Teclado y mouse disponibles.': 'Keyboard and mouse available.',
    'Usa la combinación que elegiste en Settings.': 'Use the combination you chose in Settings.',
}


def frame(stage, progress, english=False):
    def localized_text(draw, xy, value, *args):
        text(draw, xy, ENGLISH.get(value, value) if english else value, *args)

    image = Image.new('RGB', (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)
    title, accent = STAGES[stage]
    localized_text(draw, (34,21), 'LAPTOP GUARD', 24, TEXT, True)
    localized_text(draw, (601,29), 'DEMO ILUSTRADA · DATOS FICTICIOS', 15, MUTED)
    draw.line((34,66,926,66), fill='#293B55', width=1)
    localized_text(draw, (34,95), f'0{stage+1}', 64, accent, True)
    localized_text(draw, (35,182), title, 33, TEXT, True)
    subtitles = [['Tu contacto y','tu combinación.'], ['Actívalo cuando','lo necesites.'],
                 ['Un toque inicia','la alerta local.'], ['Historial continuo.','Tres clips rotativos.'],
                 ['Recupera el control','con tu combinación.']]
    for i, line in enumerate(subtitles[stage]):
        localized_text(draw, (36,236+i*31), line, 22, MUTED)
    draw.rounded_rectangle((342,94,925,434), radius=20, fill=PANEL, outline='#2D4261', width=2)
    localized_text(draw, (366,113), 'Laptop Guard', 18, MUTED, True)
    draw.line((365,153,902,153), fill='#2D4261', width=1)
    if stage == 0:
        localized_text(draw, (374,174), 'Contacto de demostración', 18, MUTED)
        draw.rounded_rectangle((371,204,894,249), radius=8, fill=BG)
        localized_text(draw, (389,212), 'TU NÚMERO AQUÍ', 21, TEXT, True)
        localized_text(draw, (374,267), 'Combinación de ejemplo', 18, MUTED)
        pill(draw, (372,300,627,344), 'Ctrl  +  Shift  +  Z')
        localized_text(draw, (374,378), 'Al guardar, la protección se activa.', 18, AMBER)
    elif stage == 1:
        pill(draw, (374,180,584,225), ENGLISH['PROTECCIÓN ACTIVA'] if english else 'PROTECCIÓN ACTIVA', GREEN)
        shield(draw, 602,263,0.9,GREEN)
        localized_text(draw, (374,366), 'También: activación automática a los 15 min*', 19, MUTED)
        localized_text(draw, (36,366), '*Automático: Windows', 16, MUTED)
    elif stage == 2:
        draw.rounded_rectangle((364,170,903,413), radius=10, fill='#05080D', outline=RED, width=2)
        lines = [('SYSTEM BREACH DETECTED',24), ('ALL FILES WILL BE PERMANENTLY',17),
                 ('DELETED IN 2 HOURS.',17), ('Call YOUR NUMBER to avoid data loss.',18),
                 ('Do NOT turn off the computer.',18)]
        for i, (line, size) in enumerate(lines):
            localized_text(draw, (389,190+i*37), line, size, RED, i==0)
        localized_text(draw, (36,366), 'Aviso ficticio:', 17, AMBER, True)
        localized_text(draw, (36,392), 'no borra archivos.', 17, MUTED)
    elif stage == 3:
        for i, label in enumerate(['logs / guard.jsonl  ·  historial', 'videos / intruder_1.mp4',
                                   'videos / intruder_2.mp4', 'videos / intruder_3.mp4']):
            y = 178+i*49
            draw.rounded_rectangle((369,y,895,y+39), radius=7, fill=BG)
            localized_text(draw, (385,y+6), label, 19, AMBER if i==0 else TEXT)
        localized_text(draw, (374,387), 'El siguiente clip reemplaza al más antiguo.', 18, MUTED)
    else:
        pill(draw, (374,184,632,230), 'Ctrl  +  Shift  +  Z', GREEN)
        localized_text(draw, (375,266), 'Alarma detenida', 28, GREEN, True)
        localized_text(draw, (375,314), 'Teclado y mouse disponibles.', 22, TEXT)
        localized_text(draw, (375,371), 'Usa la combinación que elegiste en Settings.', 18, MUTED)
    for index in range(5):
        x = 35+index*181
        color = STAGES[index][1] if index <= stage else '#293B55'
        draw.rounded_rectangle((x,475,x+163,481), radius=3, fill=color)
        if index == stage:
            draw.rounded_rectangle((x,475,x+max(3,int(163*progress)),481), radius=3, fill=TEXT)
        localized_text(draw, (x,496), STAGES[index][0], 17, color)
    return image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video', type=Path)
    parser.add_argument('--language', choices=('es', 'en'), default='es',
                        help='Walkthrough language; outputs demo.gif or demo-en.gif')
    args = parser.parse_args()
    assets = ROOT / 'docs' / 'assets'
    assets.mkdir(parents=True, exist_ok=True)
    if args.language == 'es':
        header().save(assets / 'hero.png')
    header(english=True).save(assets / 'hero-en.png')
    frames = [frame(stage, index/17, english=args.language == 'en') for stage in range(5) for index in range(18)]
    gif_frames = [item.quantize(colors=96) for item in frames]
    gif_name = 'demo-en.gif' if args.language == 'en' else 'demo.gif'
    # GIF delays use hundredths of a second; distribute rounding over the timeline.
    durations = [round((i+1)*100/FPS)*10 - round(i*100/FPS)*10 for i in range(len(frames))]
    gif_frames[0].save(ROOT / gif_name, save_all=True, append_images=gif_frames[1:],
                       duration=durations if args.language == 'en' else round(1000/FPS),
                       loop=0, optimize=True)
    if args.video:
        ffmpeg = shutil.which('ffmpeg')
        if not ffmpeg:
            raise RuntimeError('FFmpeg is required only for the optional MP4')
        args.video.parent.mkdir(parents=True, exist_ok=True)
        process = subprocess.Popen([ffmpeg,'-hide_banner','-loglevel','error','-y',
            '-f','rawvideo','-pix_fmt','rgb24','-s',f'{WIDTH}x{HEIGHT}','-r',str(FPS),
            '-i','-','-an','-c:v','libx264','-crf','22','-pix_fmt','yuv420p',
            '-movflags','+faststart',str(args.video)], stdin=subprocess.PIPE)
        try:
            for item in frames:
                process.stdin.write(item.tobytes())
        finally:
            process.stdin.close()
        if process.wait() != 0:
            raise RuntimeError('MP4 export failed')
    print('Rendered fictional walkthrough: no desktop, webcam or personal settings accessed.')


if __name__ == '__main__':
    main()
