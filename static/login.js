const message = document.getElementById('message');
const status = document.getElementById('status');
const image = document.getElementById('qr');
const generate = document.getElementById('generate');
let timer;

async function request(path, method = 'GET') {
  const response = await fetch(path, {method, headers: {'X-Requested-With': 'BiliCookie'}});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || '请求失败');
  return data;
}

async function showStatus() {
  const data = await request('/api/status');
  status.textContent = `登录状态：${data.logged_in ? '已登录' : '未登录或尚未验证'}\n` +
    `最近检查：${data.last_check ? new Date(data.last_check * 1000).toLocaleString() : '尚未检查'}\n` +
    (data.message || '');
}

async function poll() {
  try {
    const data = await request('/api/login/poll', 'POST');
    message.textContent = data.message;
    if (data.code === 0 || data.code === 86038) {
      image.hidden = true;
      await showStatus();
      return;
    }
    timer = setTimeout(poll, 2500);
  } catch (error) {
    message.textContent = error.message + '；请重新生成二维码重试。';
  }
}

generate.onclick = async () => {
  clearTimeout(timer);
  generate.disabled = true;
  image.hidden = true;
  try {
    const data = await request('/api/login/qr', 'POST');
    image.src = data.image;
    image.hidden = false;
    message.textContent = '等待扫码，二维码约三分钟有效。';
    timer = setTimeout(poll, 2500);
  } catch (error) {
    message.textContent = error.message;
  } finally {
    generate.disabled = false;
  }
};

document.getElementById('check').onclick = async function () {
  this.disabled = true;
  try {
    await request('/api/check', 'POST');
    await showStatus();
  } catch (error) {
    message.textContent = error.message;
  } finally {
    this.disabled = false;
  }
};
showStatus().catch(error => { message.textContent = error.message; });
