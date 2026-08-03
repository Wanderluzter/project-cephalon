// Project ORDIS — Weekly Digest page.

$('#weekly-regenerate')?.addEventListener('click', async () => {
  const btn = $('#weekly-regenerate');
  const status = $('#weekly-status');
  btn.disabled = true;
  status.textContent = 'Regenerating…';
  try {
    const res = await fetch('/api/weekly-image/regenerate', { method: 'POST' });
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    status.textContent = 'Regenerated.';
    // Cache-bust so the browser actually reloads the new image.
    const img = $('#weekly-image');
    if (img) img.src = img.src.split('?')[0] + '?t=' + Date.now();
  } catch (err) {
    status.textContent = `Regeneration failed: ${err.message}`;
  } finally {
    btn.disabled = false;
  }
});
