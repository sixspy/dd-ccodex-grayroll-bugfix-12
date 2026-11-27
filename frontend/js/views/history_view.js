import { api } from "../api.js";
const { ref, onMounted } = Vue;
export const HistoryView = {
  setup() {
    const items = ref([]); const err = ref("");
    async function reload() {
      try { items.value = (await api("/api/history")).items || []; }
      catch (e) { err.value = e.message || String(e); }
    }
    function fmtTime(ts) {
      if (!ts) return "";
      try { return new Date(ts * 1000).toLocaleString(); } catch { return ""; }
    }
    function actionLabel(it) {
      if (it.entry_type === "contention" || it.action === "lock_lost") return "抢锁失败";
      return it.action;
    }
    onMounted(reload);
    return { items, err, reload, fmtTime, actionLabel };
  },
  template: `
  <div class="panel">
    <h2>变更历史 · 台账</h2>
    <p class="hint">正式变更与抢锁败方争用痕同账联查；争用痕票号 <code>lose-ID</code> 与抢败返回句、总览败方账同票。败方不写正式区。</p>
    <div class="err" v-if="err">{{ err }}</div>
    <table>
      <thead><tr><th>时间 / 动作</th><th>开关</th><th>环境</th><th>详情</th><th>操作者(败方)</th></tr></thead>
      <tbody>
        <tr v-for="it in items" :key="it.id" :style="it.entry_type==='contention' ? 'background:rgba(240,113,120,0.06)' : ''">
          <td>
            <div>{{ actionLabel(it) }}
              <span class="pill danger" v-if="it.entry_type==='contention' || it.action==='lock_lost'">争用痕·败方账</span>
            </div>
            <div class="muted" style="font-size:0.74rem">{{ fmtTime(it.created_at) }}</div>
          </td>
          <td>{{ it.flag_key || '-' }}</td>
          <td>{{ it.env_code || '-' }}</td>
          <td>
            <div>{{ it.detail }}</div>
            <div class="muted" style="font-size:0.76rem" v-if="it.entry_type==='contention'">
              票 <code>{{ it.ticket || ('lose-' + it.mark_id) }}</code> · 胜方 <b>{{ it.winner }}</b> · 资源 <code>{{ it.lock_key }}</code>
            </div>
          </td>
          <td>{{ it.actor }}</td>
        </tr>
      </tbody>
    </table>
    <button class="btn secondary" style="margin-top:0.7rem" @click="reload">刷新</button>
  </div>`
};
