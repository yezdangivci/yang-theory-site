#!/usr/bin/env python3
"""Browser checks for the pinned, native-scroll, single-movie landing hero."""
import asyncio
import json
import sys
from pathlib import Path
from PIL import Image, ImageChops
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
EDIT = json.loads((ROOT / 'public/film/yang-theory-film.json').read_text())
OUT = Path('/tmp/yang-single-film-browser-checks')
OUT.mkdir(exist_ok=True)


async def geometry(page):
    return await page.evaluate('''() => {
      const stage=document.querySelector('#filmStage'), section=document.querySelector('#film');
      return {start:section.getBoundingClientRect().top+scrollY,
              span:stage.parentElement.offsetHeight-stage.offsetHeight};
    }''')


async def visit(page, time):
    bounds = await geometry(page)
    p = min(1, max(0, time/(EDIT['duration']-1/EDIT['fps'])))
    await page.evaluate('({start,span,p}) => scrollTo(0,start+span*p)', {**bounds, 'p':p})
    try:
        await page.wait_for_function('''(p) => {
          const s=document.querySelector('#filmStage'), v=document.querySelector('#filmVideo');
          return Math.abs(Number(s.dataset.progress)-p)<.0006 && !v.seeking
            && Math.abs(v.currentTime-Number(s.dataset.desiredTime))<.035
            && Math.abs(Number(s.dataset.frameTime)-Number(s.dataset.desiredTime))<.035;
        }''', arg=p, timeout=15000)
    except Exception:
        print("Seek diagnostic", await page.evaluate("() => ({scroll:scrollY, stage:document.querySelector('#filmStage').dataset, current:document.querySelector('#filmVideo').currentTime, seeking:document.querySelector('#filmVideo').seeking})"), "requested", time, p, bounds, flush=True)
        raise
    await page.wait_for_timeout(70)
    return await page.evaluate('''() => ({
      time:document.querySelector('#filmVideo').currentTime,
      title:document.querySelector('#filmTitle').textContent,
      scene:document.querySelector('#filmStage').dataset.scene,
      progress:Number(document.querySelector('#filmStage').dataset.progress)
    })''')


async def main(base):
    failures=[]; requests=set()
    async with async_playwright() as p:
        browser=await p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox','--disable-dev-shm-usage'])
        page=await browser.new_page(viewport={'width':1440,'height':900})
        page.on('pageerror',lambda error:failures.append(str(error)))
        page.on('response',lambda response:failures.append(f'{response.status} {response.url}') if response.status>=400 else None)
        page.on('request',lambda request:requests.add(request.url) if '.mp4' in request.url else None)
        await page.goto(base+'/',wait_until='domcontentloaded')
        await page.wait_for_selector('#filmStage.is-ready')
        assert await page.locator('video').count()==1
        assert await page.locator('canvas').count()==0
        assert await page.locator('#filmVideo').evaluate('(v) => v.paused && v.videoWidth===1920 && v.videoHeight===1080 && v.currentSrc.includes("yang-theory-scrub.mp4")')
        observations=[]
        for time in [0,7,14.8,15.3,20.05,20.3,23,24.6,24.8,32,39.4,39.6,44.95,45.33,48,51]:
            sample=await visit(page,time);observations.append(sample)
            assert abs(sample['time']-time)<.045
            await page.locator('#filmStage').screenshot(path=str(OUT/f'desktop-{time:.2f}.png'))
        await visit(page,32)
        await page.locator('#filmStage').screenshot(path=str(OUT/'forward.png'))
        await visit(page,46)
        await visit(page,32)
        await page.locator('#filmStage').screenshot(path=str(OUT/'reverse.png'))
        assert ImageChops.difference(Image.open(OUT/'forward.png'),Image.open(OUT/'reverse.png')).getbbox() is None
        before=await page.locator('#filmVideo').evaluate('(v) => v.currentTime')
        await page.wait_for_timeout(600)
        assert await page.locator('#filmVideo').evaluate('(v) => v.currentTime')==before
        await page.evaluate('window.nativeScrollEnded=false; addEventListener("scrollend",()=>window.nativeScrollEnded=true,{once:true});')
        await page.mouse.wheel(200,500)
        await page.wait_for_function('(t) => scrollY>0 && document.querySelector("#filmVideo").currentTime>t',arg=before)
        await page.wait_for_function('window.nativeScrollEnded')
        assert await page.locator('#filmVideo').evaluate('(v) => v.paused')
        before=await page.evaluate('scrollY')
        await page.evaluate('window.nativeScrollEnded=false; addEventListener("scrollend",()=>window.nativeScrollEnded=true,{once:true});')
        await page.keyboard.press('ArrowDown')
        await page.wait_for_function('(y) => scrollY>y',arg=before)
        await page.wait_for_function('window.nativeScrollEnded')
        await visit(page,51)
        assert await page.locator('#filmTitle').inner_text()=='Behind the world'
        await page.locator('#filmCta').click()
        await page.wait_for_function('location.hash==="#objects" && document.querySelector("#objects").getBoundingClientRect().top<200')
        assert await page.locator('#objectsTitle').is_visible()
        assert await page.locator('#journey .journey-links a').count()==6
        assert len(requests)==1,requests
        await page.close()

        mobile=await browser.new_page(viewport={'width':390,'height':844},device_scale_factor=3,is_mobile=True,has_touch=True)
        mobile.on('pageerror',lambda error:failures.append(str(error)))
        await mobile.goto(base+'/',wait_until='domcontentloaded')
        await mobile.wait_for_selector('#filmStage.is-ready')
        assert await mobile.evaluate('document.documentElement.scrollWidth<=innerWidth')
        for time in [7,17,22,32,41,51]:
            await visit(mobile,time)
            await mobile.locator('#filmStage').screenshot(path=str(OUT/f'mobile-{time:.2f}.png'))
            assert await mobile.locator('video').count()==1
            assert await mobile.evaluate('''() => {
              const copy=document.querySelector('#filmCopy').getBoundingClientRect();
              const video=document.querySelector('#filmVideo').getBoundingClientRect();
              const movieHeight=video.width*9/16;
              return copy.top >= video.top+(video.height+movieHeight)/2;
            }''')
        await mobile.set_viewport_size({'width':844,'height':390})
        await mobile.wait_for_timeout(250)
        await visit(mobile,32)
        await mobile.locator('#filmStage').screenshot(path=str(OUT/'mobile-landscape.png'))
        await mobile.close()

        reduced=await browser.new_page(viewport={'width':1280,'height':800},reduced_motion='reduce')
        await reduced.goto(base+'/',wait_until='domcontentloaded')
        await reduced.wait_for_selector('#filmStage.is-ready')
        g=await geometry(reduced)
        await reduced.evaluate('({start,span})=>scrollTo(0,start+span*.62)',g)
        await reduced.wait_for_function('(t)=>Math.abs(document.querySelector("#filmVideo").currentTime-t)<.035',arg=EDIT['starts']['Ophelia']+2)
        assert await reduced.locator('video').count()==1
        assert not failures,failures
        await browser.close()
        print(json.dumps({'passed':['one paused scrub movie, no canvas','all scenes and optical events','pixel-identical reverse scroll','no idle drift','native wheel and keyboard','maker CTA / unchanged lower page','mobile cinema layout / no copy overlap','landscape resize','reduced motion','no browser errors or missing resources'], 'distinct_movie_requests':list(requests),'observations':observations},indent=2))


if __name__=='__main__':
    asyncio.run(main((sys.argv[1] if len(sys.argv)>1 else 'http://127.0.0.1:4175').rstrip('/')))
