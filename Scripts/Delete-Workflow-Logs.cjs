// SPDX-License-Identifier: MIT
// Deletes logs only; never deletes runs, artifacts, releases or caches.
module.exports = async ({ github, context, core }) => {
  const { owner, repo } = context.repo;
  // No status/search filters: those impose a 1,000-result search limit.
  const runs = await github.paginate(github.rest.actions.listWorkflowRunsForRepo, {
    owner, repo, per_page: 100
  });
  const counts = { deleted: 0, unavailable: 0, skipped: 0, failed: 0 };
  const seen = new Set();
  for (const run of runs) {
    if (seen.has(run.id)) continue;
    seen.add(run.id);
    if (String(run.id) === String(context.runId) || run.status !== 'completed') {
      counts.skipped++;
      continue;
    }
    try {
      await github.rest.actions.deleteWorkflowRunLogs({ owner, repo, run_id: run.id });
      counts.deleted++;
      core.info('Deleted logs for run ' + run.id);
    } catch (error) {
      if (error.status === 404 || error.status === 410) {
        counts.unavailable++;
        core.info('Logs unavailable for run ' + run.id);
      } else {
        counts.failed++;
        core.error('Could not delete logs for run ' + run.id + ': ' + error.message);
        // Stop on authentication or rate-limit errors instead of flooding the API.
        if ([401, 403, 429].includes(error.status)) break;
      }
    }
  }
  await core.summary
    .addHeading('Workflow 日志清理结果')
    .addTable([
      [{ data: '项目', header: true }, { data: '数量', header: true }],
      ['已删除日志的运行', String(counts.deleted)],
      ['日志已不存在或不可用', String(counts.unavailable)],
      ['跳过当前清理任务及未完成任务', String(counts.skipped)],
      ['删除失败', String(counts.failed)]
    ])
    .addRaw('\n仅删除日志，运行记录、Artifacts、Releases 和缓存均保留。\n')
    .write();
  if (counts.failed) core.setFailed('部分日志未能删除，请查看错误信息后重试。');
  return counts;
};
