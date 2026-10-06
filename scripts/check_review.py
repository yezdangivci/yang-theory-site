#!/usr/bin/env python3
"""Exercise the built single-movie review player in a real Chromium browser."""
import asyncio
import json
import sys
from pathlib import Path
from playwright.async_api import async_playwright


async def check(base):
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path='/usr/bin/chromium',
            args=['--no-sandbox', '--disable-dev-shm-usage'])
        failures = []
        page = await browser.new_page(viewport={'width': 1440, 'height': 1050})
        page.on('pageerror', lambda error: failures.append(str(error)))
        page.on('response', lambda response: failures.append(f'{response.status} {response.url}') if response.status >= 400 else None)
        await page.goto(base + '/review.html', wait_until='domcontentloaded')
        await page.wait_for_function('document.querySelector("video").readyState >= 2')
        assert await page.locator('video').count() == 1
        assert await page.locator('canvas').count() == 0
        assert await page.locator('video').evaluate('(v) => v.controls && v.videoWidth === 1920 && v.videoHeight === 1080 && Math.abs(v.duration - 31.2) < .01')
        await page.locator('#playFilm').click()
        await page.wait_for_function('document.querySelector("video").currentTime > 1')
        await page.locator('#pauseFilm').click()
        paused_at = await page.locator('video').evaluate('(v) => v.currentTime')
        await page.wait_for_timeout(300)
        assert await page.locator('video').evaluate('(v) => v.paused')
        assert abs(await page.locator('video').evaluate('(v) => v.currentTime') - paused_at) < .03
        await page.locator('#replayFilm').click()
        await page.wait_for_function('document.querySelector("video").currentTime < 1 && !document.querySelector("video").paused')
        await page.wait_for_function('document.querySelector("video").ended', timeout=60000)
        quality = await page.locator('video').evaluate('(v) => { const q=v.getVideoPlaybackQuality(); return {time:v.currentTime, total:q.totalVideoFrames, dropped:q.droppedVideoFrames}; }')
        assert quality['total'] >= 930
        assert quality['dropped'] / quality['total'] < .05
        assert await page.locator('#beatTitle').inner_text() == 'Behind the world'
        assert await page.locator('#playFilm').is_visible()
        for time in [7.1, 10.5, 15.2, 20.8, 24.9, 28.6]:
            await page.locator('video').evaluate('(v,t) => {v.currentTime=t;}', time)
            await page.wait_for_function('(t) => {const v=document.querySelector("video"); return !v.seeking && Math.abs(v.currentTime-t)<.02;}', arg=time)
            assert not await page.locator('#pauseFilm').is_disabled()
            assert not await page.locator('#playFilm').is_visible()
        assert not failures, failures
        await page.screenshot(path='/tmp/yang-review-desktop.png', full_page=True)
        await page.goto(base + '/', wait_until='domcontentloaded')
        assert await page.locator('#playFilm').is_visible()
        await page.close()
        mobile = await browser.new_page(viewport={'width': 390, 'height': 844}, device_scale_factor=3, is_mobile=True, has_touch=True)
        mobile.on('pageerror', lambda error: failures.append(str(error)))
        await mobile.goto(base + '/review.html', wait_until='domcontentloaded')
        assert await mobile.evaluate('document.documentElement.scrollWidth <= innerWidth')
        await mobile.locator('#playFilm').click()
        await mobile.wait_for_function('document.querySelector("video").currentTime > 3')
        await mobile.locator('#pauseFilm').click()
        assert await mobile.locator('video').evaluate('(v) => v.paused')
        await mobile.locator('#replayFilm').click()
        await mobile.wait_for_function('document.querySelector("video").currentTime < 1 && !document.querySelector("video").paused')
        await mobile.screenshot(path='/tmp/yang-review-mobile.png', full_page=True)
        assert not failures, failures
        await browser.close()
        print(json.dumps({'passed': ['single video / no canvas', '1080p30 duration', 'normal uninterrupted playback', 'pause', 'replay', 'scrub / seek', 'root entry', 'mobile playback and layout', 'no missing resources or browser errors'], 'playback_quality': quality}, indent=2))


if __name__ == '__main__':
    asyncio.run(check((sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:4175').rstrip('/')))
