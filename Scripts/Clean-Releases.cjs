// SPDX-License-Identifier: MIT
// Keeps the newest releases per build line and deletes the older ones.
//
// Every build stamps its release title with WRT_DATE, so the title ends in a
// timestamp:
//   ZN-M2-WIFI-NO-VIKINGYFY-owrt-26.11.07-15.29.06     (yy.mm.dd-hh.mm.ss)
//   Fine3399-OPhub-OWRT-2026.11.08-02.24.49           (yyyy.mm.dd-hh.mm.ss)
// Everything before the timestamp names one device/build line, which is the
// grouping key. Each line keeps its newest KEEP releases, so no line ever
// loses its last release; older ones are deleted, oldest first.
//
// Titles without a timestamp are left alone and reported, so a new naming
// scheme never gets swept away by surprise.
module.exports = async ({ github, context, core, keep, dryRun, deleteTags }) => {
  const { owner, repo } = context.repo;
  const keepCount = Math.max(1, Number(keep) || 2);
  const isDryRun = String(dryRun) === 'true';
  const removeTags = String(deleteTags) !== 'false';
  const STAMP = /^(.*?)-(\d{2,4})\.(\d{2})\.(\d{2})-(\d{2})\.(\d{2})\.(\d{2})$/;

  const releases = await github.paginate(github.rest.repos.listReleases, {
    owner, repo, per_page: 100
  });

  // The release GitHub currently labels "Latest" is never deleted, even if a
  // newer timestamp exists in the same group.
  let latestId = null;
  try {
    const { data } = await github.rest.repos.getLatestRelease({ owner, repo });
    latestId = data.id;
  } catch (error) {
    if (error.status !== 404) throw error;
  }

  const groups = new Map();
  const untitled = [];
  for (const release of releases) {
    const title = release.name || release.tag_name || '';
    const match = STAMP.exec(title);
    if (!match) {
      untitled.push(title);
      continue;
    }
    const [, line, y, mo, d, h, mi, s] = match;
    const year = y.length === 2 ? 2000 + Number(y) : Number(y);
    const stampedAt = Date.UTC(year, Number(mo) - 1, Number(d), Number(h), Number(mi), Number(s));
    if (!groups.has(line)) groups.set(line, []);
    groups.get(line).push({ release, stampedAt });
  }

  const counts = { deleted: 0, wouldDelete: 0, unavailable: 0, kept: 0, skipped: 0, failed: 0 };
  const deletedTitles = [];

  for (const [line, entries] of groups) {
    entries.sort((a, b) =>
      b.stampedAt - a.stampedAt ||
      Date.parse(b.release.created_at) - Date.parse(a.release.created_at) ||
      b.release.id - a.release.id
    );
    for (const [index, entry] of entries.entries()) {
      const { release } = entry;
      if (index < keepCount || release.id === latestId) {
        counts.kept++;
        continue;
      }
      if (isDryRun) {
        counts.wouldDelete++;
        core.info('[dry-run] would delete ' + release.name + ' (' + release.tag_name + ')');
        continue;
      }
      try {
        await github.rest.repos.deleteRelease({ owner, repo, release_id: release.id });
        counts.deleted++;
        deletedTitles.push(release.name || release.tag_name);
        core.info('Deleted release ' + release.name + ' in group ' + line);
        if (removeTags && release.tag_name) {
          try {
            await github.rest.git.deleteRef({ owner, repo, ref: 'tags/' + release.tag_name });
          } catch (error) {
            // The tag can already be gone, or still referenced elsewhere.
            if (![404, 422].includes(error.status)) {
              core.warning('Release deleted but tag ' + release.tag_name + ' remains: ' + error.message);
            }
          }
        }
      } catch (error) {
        if (error.status === 404 || error.status === 410) {
          counts.unavailable++;
          core.info('Release unavailable: ' + release.name);
        } else {
          counts.failed++;
          core.error('Could not delete release ' + release.name + ': ' + error.message);
          if ([401, 403, 429].includes(error.status)) return counts;
        }
      }
    }
  }

  if (untitled.length) {
    core.info('Left alone, title has no timestamp suffix: ' + untitled.join(', '));
  }

  await core.summary
    .addHeading('Release 清理结果')
    .addTable([
      [{ data: '项目', header: true }, { data: '数量', header: true }],
      ['已删除 Release', String(counts.deleted)],
      ['预演将删除（dry-run）', String(counts.wouldDelete)],
      ['Release 已不存在', String(counts.unavailable)],
      ['保留', String(counts.kept)],
      ['删除失败', String(counts.failed)]
    ])
    .addRaw('\n每种标题（时间后缀之前的部分）保留最新 ' + keepCount + ' 个，其余按时间后缀从旧到新删除；' +
      'GitHub 标记为 Latest 的 Release 永不删除；没有时间后缀的标题不参与清理。\n')
    .write();

  if (counts.failed) core.setFailed('部分 Release 未能删除，请查看错误信息后重试。');
  return counts;
};
