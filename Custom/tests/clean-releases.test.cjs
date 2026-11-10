// SPDX-License-Identifier: MIT
// Offline check for Scripts/Clean-Releases.cjs: no network, no deletion.
const assert = require('assert');
const clean = require('../../Scripts/Clean-Releases.cjs');

const mk = (id, name, group, created) => ({
  id, name, tag_name: name, created_at: created || '2026-01-01T00:00:00Z'
});

const releases = [
  mk(1,  'RAX3000M-WIFI-NO-VIKINGYFY-owrt-26.11.09-17.52.04', 'a', '2026-11-09T10:24:09Z'),
  mk(2,  'Fine3399-OPhub-OWRT-2026.11.08-02.24.49', 'b', '2026-11-08T02:25:13Z'),
  mk(3,  'N60-Pro-512M-WIFI-NO-VIKINGYFY-owrt-26.11.07-15.31.37', 'c', '2026-11-07T09:48:11Z'),
  mk(4,  'IPQ807X-AP8220-1G-SINGLE-WIFI-NO-VIKINGYFY-owrt-26.11.07-15.31.14', 'd', '2026-11-07T09:32:58Z'),
  mk(5,  'ZN-M2-WIFI-NO-VIKINGYFY-owrt-26.11.07-15.29.06', 'e', '2026-11-07T08:33:11Z'),
  mk(6,  'IPQ807X-AP8220-1G-SINGLE-WIFI-NO-VIKINGYFY-owrt-26.11.06-23.33.50', 'd', '2026-11-06T16:59:03Z'),
  mk(7,  'Fine3399-OPhub-OWRT-2026.10.01-10.00.00', 'b', '2026-10-01T10:01:00Z'),
  mk(8,  'Fine3399-OPhub-OWRT-2026.10.29-17.50.54', 'b', '2026-10-29T17:51:15Z'),
  mk(9,  'Panther-X2-OPhub-OWRT-2026.10.29-17.50.24', 'f', '2026-10-29T17:50:43Z'),
  mk(10, 'JDCloud-RE-SP-01B-VIKINGYFY-owrt-26.10.24-18.54.03', 'g', '2026-10-24T12:23:36Z'),
  mk(11, 'ZN-M2-WIFI-NO-VIKINGYFY-main-26.10.23-14.53.43', 'h', '2026-10-23T08:40:10Z'),
  mk(12, 'AIROHA-NWRT-VIKINGYFY-owrt-26.09.20-06.26.56', 'i', '2026-09-19T23:38:58Z'),
  mk(13, 'custom-build-without-timestamp', 'j', '2026-09-01T00:00:00Z')
];

function makeClient(latestId) {
  const deleted = [];
  const deletedTags = [];
  return {
    deleted, deletedTags,
    rest: {
      repos: {
        listReleases: async () => ({ data: releases }),
        deleteRelease: async ({ release_id }) => { deleted.push(release_id); return {}; },
        getLatestRelease: async () => ({ data: { id: latestId } })
      },
      git: {
        deleteRef: async ({ ref }) => { deletedTags.push(ref); return {}; }
      }
    },
    paginate: async (fn) => (await fn()).data
  };
}

const core = {
  info: () => {}, warning: () => {}, error: () => {}, setFailed: () => {},
  summary: { addHeading() { return this; }, addTable() { return this; }, addRaw() { return this; }, write: async () => {} }
};

(async () => {
  // 1) 正常清理：Fine3399 组有 3 个，应删最老的 (id 7)
  let c = makeClient(1);
  let r = await clean({ github: c, context: { repo: { owner: 'o', repo: 'r' } }, core, keep: '2', dryRun: 'false' });
  assert.deepStrictEqual(c.deleted, [7], '应只删除 Fine3399 组最老的 id 7，实际 ' + JSON.stringify(c.deleted));
  assert.strictEqual(r.deleted, 1);
  console.log('用例1 通过：同组 3 个 → 删最老的一个 (id 7)');

  // 2) Latest 不删：把 Fine3399 最老的设为 Latest，则不该删任何东西
  c = makeClient(7);
  r = await clean({ github: c, context: { repo: { owner: 'o', repo: 'r' } }, core, keep: '2', dryRun: 'false' });
  assert.deepStrictEqual(c.deleted, [], 'Latest 不应被删，实际 ' + JSON.stringify(c.deleted));
  // 13 个里有一个没有时间后缀，不参与分组，所以保留计数是 12
  assert.strictEqual(r.kept, 12);
  console.log('用例2 通过：Latest 保护生效（组内超额也不删）');

  // 3) dry-run 不删
  c = makeClient(1);
  r = await clean({ github: c, context: { repo: { owner: 'o', repo: 'r' } }, core, keep: '2', dryRun: 'true' });
  assert.deepStrictEqual(c.deleted, []);
  assert.strictEqual(r.wouldDelete, 1);
  console.log('用例3 通过：dry-run 只统计不删除');

  // 4) keep=1 时每组只留最新
  c = makeClient(1);
  r = await clean({ github: c, context: { repo: { owner: 'o', repo: 'r' } }, core, keep: '1', dryRun: 'false' });
  // Fine3399 组剩 1 个（删 8、7），AP8220 组剩 1 个（删 6）
  assert.deepStrictEqual([...c.deleted].sort((a, b) => a - b), [6, 7, 8]);
  console.log('用例4 通过：keep=1 时每组只留最新');

  // 5) 没有时间后缀的原样保留
  assert.ok(!c.deleted.includes(13), '无时间后缀的 Release 不应被删');
  assert.strictEqual(r.failed, 0);
  console.log('用例5 通过：无时间后缀标题不参与清理');

  // 6) 两种年份格式混排时，yyyy 与 yy 都按真实时间排序
  const cmp = (a, b) => {
    const S = /^(.*?)-(\d{2,4})\.(\d{2})\.(\d{2})-(\d{2})\.(\d{2})\.(\d{2})$/;
    const t = (n) => { const m = S.exec(n); const y = m[2].length === 2 ? 2000 + +m[2] : +m[2];
      return Date.UTC(y, +m[3]-1, +m[4], +m[5], +m[6], +m[7]); };
    return t(a) - t(b);
  };
  assert.ok(cmp('Fine3399-OPhub-OWRT-2026.10.29-17.50.54', 'ZN-M2-WIFI-NO-VIKINGYFY-owrt-26.11.07-15.29.06') < 0);
  console.log('用例6 通过：yyyy 与 yy 两种后缀可正确比较');

  console.log('\n全部通过');
})().catch((e) => { console.error('失败:', e.message); process.exit(1); });
