"""Deterministic local browser evidence capture for generated web artifacts."""
from __future__ import annotations
import functools,json,threading
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from pathlib import Path
from .artifacts import evidence
from .contracts import Execution

class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self,*args):pass

async def capture(workspace:Path,output:Path,candidate_id:str):
    from playwright.async_api import async_playwright
    server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(QuietHandler,directory=str(workspace)))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    errors=[];items=[];ok=False
    try:
        async with async_playwright() as p:
            browser=await p.chromium.launch(channel='chrome',headless=True)
            try:
                context=await browser.new_context(viewport={'width':1280,'height':720})
                # Runtime is offline except the local artifact server.
                origin=f'http://127.0.0.1:{server.server_port}'
                async def route(request):
                    if request.request.url.startswith(origin+'/') or request.request.url.startswith(('data:','blob:')):await request.continue_()
                    else:await request.abort()
                await context.route('**/*',route)
                page=await context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
                response=await page.goto(origin+'/index.html',wait_until='networkidle',timeout=30000)
                await page.screenshot(path=str(output/'initial.png'))
                for i,key in enumerate(['a','a','l']):
                    await page.keyboard.press(key);await page.wait_for_timeout(2500 if i==0 else 1200)
                    await page.screenshot(path=str(output/f'action-{i}.png'))
                await page.wait_for_timeout(46000)
                await page.screenshot(path=str(output/'results.png'))
                await page.keyboard.press('a');await page.wait_for_timeout(2500)
                await page.screenshot(path=str(output/'retry.png'))
                ok=bool(response and response.ok) and not errors
            finally:await browser.close()
    except Exception as exc:errors.append(f'{type(exc).__name__}: {exc}')
    finally:server.shutdown();server.server_close();thread.join(timeout=2)
    (output/'browser.json').write_text(json.dumps({'errors':errors,'actions':['a','a','l'],'viewport':[1280,720]},indent=2))
    items=[evidence(p,output,'image',candidate_id) for p in sorted(output.glob('*.png'))]
    items.append(evidence(output/'browser.json',output,'log',candidate_id))
    return Execution(ok=ok,evidence=items,public_feedback={'browser_errors':errors,'runtime_ok':ok,'scope':'public fixed key smoke; not official replay'})
