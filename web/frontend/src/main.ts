import { createPinia } from "pinia";
import { createApp } from "vue";

// 字体自托管（P0）：从 Google Fonts CDN 改为 fontsource 构建期打包，
// 规避国内网络访问 fonts.googleapis.com 被墙导致回退系统字、破坏仪器面板气质。
// IBM Plex Mono/Sans 拉丁与数字为主；中文走 --font-sans 栈内系统 CJK 回落。
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "@fontsource/ibm-plex-mono/600.css";
import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";

import App from "./App.vue";
import router from "./router";
import "./styles/tokens.css";
import "./styles/base.css";

const app = createApp(App);
app.use(createPinia());
app.use(router);
app.mount("#app");