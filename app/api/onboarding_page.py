"""HTML for the public /onboard page (kept separate so its long CSS/JS
lines don't fight the 100-char lint on real code).
"""

ONBOARD_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Join OpsGenie</title>
<style>
  :root { --brand:#128C7E; --brand-dark:#075E54; --bg:#f4f6f8; --err:#c0392b; --ok:#128C7E; }
  * { box-sizing:border-box; }
  body { margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
         background:var(--bg); color:#1f2a33; display:flex; min-height:100vh; align-items:center; justify-content:center; padding:16px; }
  .card { background:#fff; width:100%; max-width:420px; border-radius:16px; box-shadow:0 8px 30px rgba(0,0,0,.08); padding:28px 24px; }
  .logo { font-size:26px; font-weight:700; color:var(--brand-dark); text-align:center; }
  .tag { text-align:center; color:#5b6b76; font-size:14px; margin:6px 0 22px; }
  label { display:block; font-size:13px; font-weight:600; margin:14px 0 6px; }
  input { width:100%; padding:12px 14px; border:1px solid #d7dee3; border-radius:10px; font-size:16px; }
  input:focus { outline:none; border-color:var(--brand); box-shadow:0 0 0 3px rgba(18,140,126,.15); }
  .hint { font-size:12px; color:#8a97a0; margin-top:4px; }
  button { width:100%; margin-top:22px; padding:14px; border:none; border-radius:10px; background:var(--brand);
           color:#fff; font-size:16px; font-weight:600; cursor:pointer; }
  button:disabled { opacity:.6; cursor:default; }
  #result { margin-top:16px; padding:12px 14px; border-radius:10px; font-size:14px; display:none; }
  #result.ok { display:block; background:#e8f5f2; color:var(--ok); }
  #result.err { display:block; background:#fdecea; color:var(--err); }
  .foot { text-align:center; font-size:12px; color:#98a4ac; margin-top:18px; }
</style>
</head>
<body>
  <div class="card">
    <div class="logo">OpsGenie</div>
    <div class="tag">Your daily financial assistant on WhatsApp</div>
    <form id="f">
      <label for="business_name">Business name</label>
      <input id="business_name" name="business_name" required maxlength="200" autocomplete="organization">
      <label for="owner_name">Your name</label>
      <input id="owner_name" name="owner_name" required maxlength="200" autocomplete="name">
      <label for="whatsapp_number">WhatsApp number</label>
      <input id="whatsapp_number" name="whatsapp_number" required maxlength="32" inputmode="tel"
             placeholder="+91XXXXXXXXXX">
      <div class="hint">Include your country code, e.g. +91 for India.</div>
      <label for="access_code">Access code</label>
      <input id="access_code" name="access_code" required maxlength="200" autocomplete="off">
      <div class="hint">The code shared with you by OpsGenie.</div>
      <button id="submit" type="submit">Request access</button>
    </form>
    <div id="result"></div>
    <div class="foot">You'll get a WhatsApp welcome once your access is activated.</div>
  </div>
<script>
const f = document.getElementById('f');
const res = document.getElementById('result');
const btn = document.getElementById('submit');
f.addEventListener('submit', async (e) => {
  e.preventDefault();
  btn.disabled = true; res.className = ''; res.textContent = '';
  const body = {
    business_name: f.business_name.value.trim(),
    owner_name: f.owner_name.value.trim(),
    whatsapp_number: f.whatsapp_number.value.trim(),
    access_code: f.access_code.value.trim(),
  };
  try {
    const r = await fetch('/onboard', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
    const data = await r.json();
    if (r.ok) {
      res.className = 'ok';
      res.textContent = data.message || 'Registered! You will hear from us on WhatsApp soon.';
      f.reset();
    } else {
      res.className = 'err';
      res.textContent = (data && data.detail) ? data.detail : 'Something went wrong. Please try again.';
    }
  } catch (err) {
    res.className = 'err';
    res.textContent = 'Network error. Please try again.';
  } finally {
    btn.disabled = false;
  }
});
</script>
</body>
</html>"""
