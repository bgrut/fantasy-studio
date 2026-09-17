// Which renderer does each launch mode get: the software rasterizer or the card?
import puppeteer from 'puppeteer-core';
const probe = async (label, opts) => {
  const b = await puppeteer.launch(Object.assign({ executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' }, opts));
  const p = await b.newPage();
  await p.setContent('<canvas id=c></canvas>');
  const r = await p.evaluate(() => {
    const gl = document.getElementById('c').getContext('webgl2');
    if (!gl) return 'no webgl2';
    const ext = gl.getExtension('WEBGL_debug_renderer_info');
    return ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER);
  });
  console.log(label.padEnd(28), '->', r);
  await b.close();
};
await probe('headless new, d3d11', { headless: 'new', args: ['--use-angle=d3d11', '--window-size=1280,760'] });
await probe('headless new, d3d11, gpu', { headless: 'new', args: ['--use-angle=d3d11', '--ignore-gpu-blocklist', '--enable-gpu-rasterization', '--window-size=1280,760'] });
await probe('headed, d3d11', { headless: false, args: ['--use-angle=d3d11', '--ignore-gpu-blocklist', '--window-size=1280,760', '--window-position=2000,2000'] });
