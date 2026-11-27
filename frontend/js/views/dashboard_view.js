import { api } from "../api.js";
const { ref, onMounted } = Vue;
export const DashboardView = {
  setup() {
    const data = ref(null); const health = ref(null); const err = ref("");
    const reviewMsg = ref(""); const reviewBusy = ref(false);
    async function reload() {
      err.value = "";
      try {
        health.value = await api("/api/health");
        data.value = await api("/api/dashboard");
      } catch (e) { err.value = e.message || String(e); }
    }
    async function sealReview() {
      reviewMsg.value = ""; err.value = ""; reviewBusy.value = true;
      try {
        const res = await api("/api/locks/contention/review", {
          method: "POST",
          body: JSON.stringify({ note: "总览页当班复核封账" }),
        });
        reviewMsg.value = `已复核封账至败方账 #${res.reviewed_through}（共 ${res.marks_at_review} 笔）`;
        await reload();
      } catch (e) { err.value = e.message || String(e); }
      finally { reviewBusy.value = false; }
    }
    function fmtTime(ts) {
      if (!ts) return "-";
      try { return new Date(ts * 1000).toLocaleString(); } catch { return String(ts); }
    }
    onMounted(reload);
    return { data, health, err, reviewMsg, reviewBusy, reload, sealReview, fmtTime };
  },
  template: `
  <div class="grid">
    <div class="panel span-12">
      <h2>发布控制台</h2>
      <p class="muted">{{ health && health.skeleton }}</p>
      <div class="err" v-if="err">{{ err }}</div>
    </div>
    <div class="panel span-3" v-if="data"><div class="muted">开关数</div><p class="stat">{{ data.flags }}</p></div>
    <div class="panel span-3" v-if="data"><div class="muted">已生效</div><p class="stat">{{ data.active }}</p></div>
    <div class="panel span-3" v-if="data"><div class="muted">开放影子</div><p class="stat">{{ data.open_shadows }}</p></div>
    <div class="panel span-3" v-if="data">
      <div class="muted">抢锁败方账</div>
      <p class="stat" :class="{ danger: (data.loser_count||0) > 0 }">{{ data.loser_count || 0 }}</p>
      <span class="pill ok" v-if="data.contention_reviewed">已复核（封账票号 {{ data.contention_seal_through ?? 0 }}）</span>
      <span class="pill danger" v-else>未复核 · 空账不等于已复核</span>
    </div>

    <div class="panel span-12" v-if="data">
      <h2>资源抢败记账互斥 · 败方争用痕台账</h2>
      <p class="hint">甲路径：抢败同事务落败方账并回 409 抢败句，正式区零增、影子草案也不写；败方只记争用痕。返回句票号与下表 #ID 同票，可跨历史台账联查。</p>
      <div style="display:flex;gap:1rem;align-items:center;flex-wrap:wrap;margin:0.4rem 0 0.7rem">
        <span class="muted">败方累计 <b>{{ data.loser_count || 0 }}</b></span>
        <span class="muted">未复核 <b :style="{color: (data.unreviewed_count||0) ? 'var(--danger)' : 'var(--ok)'}">{{ data.unreviewed_count || 0 }}</b></span>
        <span class="muted">不同败方 <b>{{ data.distinct_losers || 0 }}</b></span>
        <button class="btn secondary" :disabled="reviewBusy" @click="sealReview">复核封账</button>
        <span class="muted" v-if="reviewMsg" style="color:var(--ok)">{{ reviewMsg }}</span>
      </div>
      <table>
        <thead><tr><th>票号</th><th>资源锁</th><th>败方</th><th>持锁胜方</th><th>时间</th></tr></thead>
        <tbody>
          <tr v-for="m in (data.loser_ledger || [])" :key="'lose-' + m.id">
            <td><code>lose-{{ m.id }}</code></td>
            <td><code>{{ m.lock_key }}</code></td>
            <td>{{ m.loser }}</td>
            <td>{{ m.winner }}</td>
            <td>{{ fmtTime(m.created_at) }}</td>
          </tr>
          <tr v-if="!(data.loser_ledger || []).length">
            <td colspan="5" class="muted">暂无败方账；未复核封账前本页不亮「已复核」绿灯。</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="panel span-6" v-if="data">
      <h2>状态分布</h2>
      <table><thead><tr><th>状态</th><th>数量</th></tr></thead>
      <tbody><tr v-for="s in data.by_status" :key="s.status"><td>{{ s.label }}</td><td>{{ s.c }}</td></tr></tbody></table>
    </div>
    <div class="panel span-6" v-if="data">
      <h2>最近变更</h2>
      <table><thead><tr><th>动作</th><th>详情</th><th>操作者</th></tr></thead>
      <tbody><tr v-for="h in data.recent" :key="h.id"><td>{{ h.action }}</td><td>{{ h.detail }}</td><td>{{ h.actor }}</td></tr></tbody></table>
      <button class="btn secondary" style="margin-top:0.7rem" @click="reload">刷新</button>
    </div>
  </div>`
};
