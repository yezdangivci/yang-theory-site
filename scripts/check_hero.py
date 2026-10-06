"""Real-browser checks for source playback, reversible compositing and navigation."""
import base64
import hashlib
import shutil
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL=sys.argv[1] if len(sys.argv)>1 else 'http://127.0.0.1:4173'
OUT=Path('/tmp/yang-hero-checks');OUT.mkdir(exist_ok=True)
POINTS=[
    (0.,'Zaru'),(.1675,'Journey'),(.24,'Journey'),(.3075,'Seek Magic'),
    (.39,'Seek Magic'),(.4575,'Ophelia'),(.55,'Ophelia'),(.6175,'Shila'),
    (.69,'Shila'),(.765,'Burton'),(.83,'Burton'),(.96,'Behind the world'),
]
errors=[]

def attach_checks(page):
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.on('response',lambda response:errors.append(f'{response.status}: {response.url}') if response.status>=400 else None)
    page.on('console',lambda message:errors.append(message.text) if message.type=='error' else None)

def ready(page):
    # Media range buffering can keep networking active after the film is ready.
    # The application's decoded-frame readiness is the relevant criterion.
    page.goto(URL,wait_until='domcontentloaded')
    page.wait_for_selector('.film-stage.is-ready',timeout=45000)
    assert page.locator('video').count()==5
    assert page.evaluate("[...document.querySelectorAll('video')].every(v => v.videoWidth > 0 && v.videoHeight > 0 && v.paused)")
    assert not page.locator('#filmStage').get_attribute('data-error')

def seek(page,progress):
    distance=page.evaluate("document.querySelector('.pin-spacer').offsetHeight-document.querySelector('#filmStage').offsetHeight")
    page.evaluate('(y)=>window.scrollTo(0,y)',round(progress*distance))
    page.wait_for_function('(target)=>Math.abs(Number(document.querySelector("#filmStage").dataset.progress)-target)<.002',arg=progress)
    # Wait for the active videos to present decoded target frames, not just seek.
    page.wait_for_timeout(220)
    page.wait_for_function('''() => [...document.querySelectorAll('video')].every(v => !v.seeking && Math.abs(Number(v.dataset.frameTime)-v.currentTime)<.002)''',timeout=15000)
    page.wait_for_timeout(160)

def pixels(page):
    return base64.b64decode(page.evaluate('filmCanvas.toDataURL("image/png").split(",")[1]'))

def corner(page):
    return page.evaluate('''() => { const gl=filmCanvas.getContext('webgl');const pixel=new Uint8Array(4);gl.readPixels(2,2,1,1,gl.RGBA,gl.UNSIGNED_BYTE,pixel);return [...pixel]; }''')

with sync_playwright() as playwright:
    executable=shutil.which('chromium') or shutil.which('google-chrome')
    browser=playwright.chromium.launch(executable_path=executable,headless=True,args=['--no-sandbox','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader'])
    desktop=browser.new_page(viewport={'width':1440,'height':900},device_scale_factor=1)
    attach_checks(desktop);ready(desktop)
    baseline={}
    for index,(progress,name) in enumerate(POINTS):
        seek(desktop,progress)
        assert desktop.locator('#filmTitle').inner_text()==name
        image=pixels(desktop);baseline[progress]=hashlib.sha256(image).hexdigest()
        (OUT/f'{index:02d}-desktop.png').write_bytes(image)
        assert len(image)>20000,'Canvas is unexpectedly empty'
        if name=='Seek Magic' and progress==.39:assert corner(desktop)==[243,233,221,255]
        if name=='Shila' and progress==.69:assert corner(desktop)==[244,233,225,255]
    assert desktop.locator('#filmCta').is_visible()
    for progress,name in reversed(POINTS):
        seek(desktop,progress)
        assert hashlib.sha256(pixels(desktop)).hexdigest()==baseline[progress],f'Non-deterministic reverse composite at {progress}'
    # Pausing scroll cannot advance any footage or change the composition.
    seek(desktop,.4575);paused=pixels(desktop);desktop.wait_for_timeout(1100)
    assert pixels(desktop)==paused,'The edit drifts while scroll is idle'
    # Resize must retain a timeline whose progress is derived from document scroll.
    desktop.set_viewport_size({'width':1280,'height':800});desktop.wait_for_timeout(700)
    seek(desktop,.69);assert desktop.locator('#filmTitle').inner_text()=='Shila'
    assert desktop.evaluate('document.documentElement.scrollWidth<=innerWidth')
    seek(desktop,.96);desktop.locator('#filmCta').click();desktop.wait_for_timeout(500)
    assert desktop.locator('#objects').bounding_box()['y']<100
    desktop.screenshot(path=str(OUT/'lower-page.png'))
    print('PASS: desktop six beats, five midpoints, reverse pixel equality, idle stability, resize and CTA handoff',flush=True)

    mobile=browser.new_page(viewport={'width':390,'height':844},device_scale_factor=3,is_mobile=True,has_touch=True)
    attach_checks(mobile);ready(mobile)
    for progress,name in [(0,'Zaru'),(.24,'Journey'),(.39,'Seek Magic'),(.55,'Ophelia'),(.69,'Shila'),(.96,'Behind the world')]:
        seek(mobile,progress);assert mobile.locator('#filmTitle').inner_text()==name
        assert mobile.evaluate('document.documentElement.scrollWidth<=innerWidth')
        mobile.screenshot(path=str(OUT/f'mobile-{name.replace(" ","-")}.png'))
        if name=='Ophelia':assert not mobile.locator('#filmCopy').evaluate('(el)=>el.classList.contains("is-light")')
    assert mobile.locator('#filmCta').is_visible()
    # Native browser keyboard/wheel scrolling must remain effective.
    seek(desktop,.24);before=desktop.evaluate('scrollY');desktop.mouse.wheel(0,240);desktop.wait_for_timeout(500)
    assert desktop.evaluate('scrollY')>before
    before=desktop.evaluate('scrollY');desktop.keyboard.press('PageDown');desktop.wait_for_timeout(600)
    assert desktop.evaluate('scrollY')>before
    print('PASS: mobile source framing and native wheel/keyboard navigation',flush=True)

    reduced=browser.new_page(viewport={'width':1280,'height':800},reduced_motion='reduce')
    attach_checks(reduced);ready(reduced)
    times=reduced.evaluate('[...document.querySelectorAll("video")].map(v=>v.currentTime)')
    for progress,_ in POINTS:seek(reduced,progress)
    assert reduced.evaluate('[...document.querySelectorAll("video")].map(v=>v.currentTime)')==times
    assert reduced.locator('#filmTitle').inner_text()=='Behind the world'
    assert reduced.locator('#filmCta').is_visible()
    print('PASS: reduced-motion source moments and final CTA',flush=True)
    browser.close()

assert not errors,'Browser/resource errors: '+repr(errors)
print('PASS: no browser errors or missing resources; all outputs are in '+str(OUT))
