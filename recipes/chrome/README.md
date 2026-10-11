# chrome

Google Chrome stable and Node.js in one image, for headless automation with
Puppeteer or Playwright. The environment points both libraries at the system
Chrome and skips their own browser downloads.

## Use

```bash
ds run chrome                # interactive bash with node and google-chrome
ds shell chrome google-chrome --version
ds shell chrome google-chrome --headless=new --no-sandbox \
    --user-data-dir=/home/user/.config/google-chrome --dump-dom https://example.com
```

Puppeteer, from `ds run chrome`:

```bash
npm i puppeteer
node -e "const p=require('puppeteer');(async()=>{const b=await p.launch({args:['--no-sandbox','--disable-dev-shm-usage']});const pg=await b.newPage();await pg.goto('https://example.com');console.log(await pg.title());await b.close()})()"
```

Always launch Chrome with `--no-sandbox`. The container drops all capabilities
and sets `no-new-privileges`, so Chrome's sandbox can't start.
`--disable-dev-shm-usage` avoids the small default `/dev/shm`. Give the bare CLI
a `--user-data-dir` (Puppeteer and Playwright pass their own); headless Chrome
can't create its default one here. Replace `user` with your `CONTAINER_USER`.

Keep Chrome in its own service: its template mounts a private volume over
`~/.local`, which would hide tools installed into `~/.local/bin`.
