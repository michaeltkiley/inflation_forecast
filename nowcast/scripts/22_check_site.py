#!/usr/bin/env python3
"""Check the built Inflation Nowcast and Forecast page (docs/index.html + docs/data/nowcast.json, served over HTTP as on GitHub Pages) in headless Chromium: no JavaScript errors; tab switching and
#nowcast / #forecast deep links; the Nowcast tab (hero, tiles, every measure/month selection, hover and keyboard tooltips, components, track record, credits, related-work links); the Forecast tab's
existing content (banner table, chart, definitions); the author's name and disclaimer on both tabs; no horizontal scroll at phone width; dark scheme. Exit code 1 on any failure, so the daily run
flags a broken page. Needs Playwright with Chromium (pip install playwright; playwright install chromium); without it the check is skipped (exit 0, with a notice).
Usage: python scripts/22_check_site.py"""
import functools
import http.server
import socketserver
import sys
import threading

from lib_common import ROOT

DOCS = ROOT.parent / 'docs'


def serve():
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a, **k):
            pass
    handler = functools.partial(Quiet, directory=str(DOCS))
    srv = socketserver.TCPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print('Playwright is not installed: dashboard check skipped')
        return 0
    if not (DOCS / 'index.html').exists() or not (DOCS / 'data' / 'nowcast.json').exists():
        print('FAIL docs/index.html or docs/data/nowcast.json missing')
        return 1
    srv = serve()
    base = f'http://127.0.0.1:{srv.server_address[1]}/index.html'
    errs, results = [], []

    def check(name, ok, detail=''):
        results.append((name, ok))
        if not ok:
            print(f'FAIL {name} {detail}')
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={'width': 1200, 'height': 900})
        pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' and 'fonts.g' not in m.text and 'net::ERR' not in m.text and 'Failed to load resource' not in m.text else None)
        pg.goto(base + '#nowcast', wait_until='load')
        pg.wait_for_selector('#nc-body:not([hidden])', timeout=10000)
        check('deep link does not scroll the page past the header', pg.evaluate('window.scrollY') == 0)
        pg.wait_for_timeout(400)
        tip = pg.locator('#nc-tip')
        on = lambda: 'on' in (tip.get_attribute('class') or '')
        # ---- shared page chrome
        check('title and author name', 'Michael T. Kiley' in pg.title() and pg.locator('.site-nav .wordmark').inner_text() == 'Michael T. Kiley')
        check('two tabs, Nowcast selected by default', pg.locator('.tabs [role=tab]').count() == 2 and pg.locator('#tab-nowcast').get_attribute('aria-selected') == 'true' and pg.locator('#panel-nowcast').is_visible() and not pg.locator('#panel-forecast').is_visible())
        disc = pg.locator('footer.methodology .disclaimer')
        check('disclaimer visible on Nowcast tab', disc.is_visible() and 'For informational purposes only' in disc.inner_text() and 'do not reflect the views of any institution' in disc.inner_text())
        # ---- Nowcast tab
        check('hero and tiles render', pg.locator('#nc-hero .nc-fig').count() == 1 and pg.locator('.nc-tile').count() == 5)
        for meas in ['Core PCE', 'Headline PCE', 'Core CPI', 'Headline CPI']:
            pg.locator('#nc-f-measure button', has_text=meas).first.click()
            months = pg.locator('#nc-f-month button')
            for i in range(months.count()):
                months.nth(i).click()
                pg.wait_for_timeout(60)
                check(f'path chart {meas} / {months.nth(i).inner_text()}', pg.locator('#nc-path-chart svg circle').count() >= 1)
        pg.locator('#nc-f-measure button', has_text='Core PCE').first.click()
        pg.locator('#nc-f-month button').first.click()
        pg.locator('#nc-path-chart').scroll_into_view_if_needed()
        pg.wait_for_timeout(300)
        box = pg.locator('#nc-path-chart svg').bounding_box()
        pg.mouse.move(box['x'] + box['width'] * 0.5, box['y'] + box['height'] * 0.5)
        pg.wait_for_timeout(120)
        check('path chart hover tooltip', on())
        pg.mouse.move(5, 5)
        pg.locator('#nc-path-chart').focus()
        pg.keyboard.press('ArrowLeft')
        pg.wait_for_timeout(100)
        check('keyboard tooltip', on())
        rows = pg.locator('#panel-nowcast .brow')
        check('component bars', rows.count() >= 15)
        rows.nth(5).hover()
        pg.wait_for_timeout(100)
        check('bar hover tooltip', on())
        for lab in ['Headline PCE', 'Core PCE']:
            pg.locator('#nc-t-measure button', has_text=lab).click()
            pg.locator('#nc-track-chart').scroll_into_view_if_needed()
            pg.wait_for_timeout(150)
            tb = pg.locator('#nc-track-chart svg').bounding_box()
            pg.mouse.move(tb['x'] + tb['width'] * 0.4, tb['y'] + tb['height'] * 0.5)
            pg.wait_for_timeout(100)
            check(f'track chart {lab} hover', on())
        check('MAE table', pg.locator('#nc-mae tr').count() >= 7)
        credit = pg.locator('#nc-cle-credit').inner_text()
        check('Cleveland attribution', 'CC BY 4.0' in credit and 'frbc-inflationnowcast' in credit and 'No endorsement' in credit)
        check('related-work links', pg.locator('#panel-nowcast a[href*="econvitals.org"]').count() == 1 and pg.locator('#panel-nowcast a[href*="chicago-fed-letter/2026/529"]').count() == 1)
        # ---- Forecast tab (existing content)
        pg.locator('#tab-forecast').click()
        pg.wait_for_timeout(200)
        check('Forecast tab shows and deep-links', pg.locator('#panel-forecast').is_visible() and not pg.locator('#panel-nowcast').is_visible() and pg.url.endswith('#forecast'))
        check('Forecast banner table and chart intact', pg.locator('#banner-table tbody tr').count() >= 5 and pg.locator('#chart path.series-path').count() >= 5)
        check('Forecast headline text kept', 'Persistence and Expectations' in pg.locator('#panel-forecast .panel-title').inner_text())
        check('disclaimer visible on Forecast tab', pg.locator('footer.methodology .disclaimer').is_visible())
        pg.locator('#tab-nowcast').click()
        pg.wait_for_timeout(300)
        check('charts redraw when returning to Nowcast', pg.locator('#nc-path-chart svg').count() == 1 and pg.locator('#nc-path-chart svg').bounding_box()['width'] > 600)
        # ---- deep link, phone width, dark
        d = b.new_page(viewport={'width': 1200, 'height': 900})
        d.goto(base + '#forecast', wait_until='load')
        d.wait_for_timeout(300)
        check('#forecast deep link opens Forecast', d.locator('#panel-forecast').is_visible() and d.locator('#tab-forecast').get_attribute('aria-selected') == 'true')
        m = b.new_page(viewport={'width': 390, 'height': 800})
        m.goto(base + '#nowcast', wait_until='load')
        m.wait_for_timeout(500)
        sw, iw = m.evaluate('[document.documentElement.scrollWidth, window.innerWidth]')
        check('no horizontal scroll at 390px (Nowcast tab)', sw <= iw, f'{sw} > {iw}')
        f = b.new_page(viewport={'width': 390, 'height': 800})              # informational: the Forecast tab (unchanged original content) overflows by 24px because its legend row does not wrap
        f.goto(base + '#forecast', wait_until='load')
        f.wait_for_timeout(500)
        fsw = f.evaluate('document.documentElement.scrollWidth')
        if fsw > 390:
            print(f'note: Forecast tab is {fsw}px wide at a 390px viewport (pre-existing; .legend-group does not wrap)')
        dk = b.new_page(viewport={'width': 1200, 'height': 900}, color_scheme='dark')
        dk.goto(base, wait_until='load')
        dk.wait_for_timeout(400)
        check('dark scheme applies', dk.evaluate('getComputedStyle(document.body).backgroundColor').startswith('rgb(18, 22, 28)'))
        b.close()
    srv.shutdown()
    check('no JavaScript errors', not errs, str(errs[:3]))
    bad = [n for n, ok in results if not ok]
    print(f'dashboard check: {len(results) - len(bad)}/{len(results)} passed' + (f'; FAILED: {bad}' if bad else ''))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
