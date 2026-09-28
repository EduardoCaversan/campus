from campus.providers.moodle_content import announcement_index, same_origin, visible_resources


def test_visible_policy_files_and_announcement_indexes():
    html = '<main id="region-main"><a href="/mod/resource/view.php?id=12">Plano de Ensino</a><a href="/mod/forum/view.php?id=14">Avisos</a><a href="/mod/forum/view.php?id=14&mark=read">Mark</a><a href="https://evil.invalid/mod/resource/view.php?id=2">Plano</a></main>'
    found = visible_resources(html, "https://moodle.example/course/view.php?id=3", "course:X")
    assert len(found) == 2
    assert found[0]["policy_candidate"]
    assert found[1]["announcement_index"]
    assert not same_origin("http://moodle.example/file", "https://moodle.example")
    assert not same_origin("https://user@moodle.example/file", "https://moodle.example")


def test_forum_index_stable_titles_exclude_unread_counts_and_actions():
    html = '<table class="discussion-list"><tr data-discussionid="12"><th><a href="/mod/forum/discuss.php?d=12">Prazo alterado para 03/11</a></th><td>4 unread</td><td><a href="?mark=read">Mark read</a></td><td><time datetime="2026-09-20T12:00:00Z"></time></td></tr></table>'
    facts = announcement_index(html, "https://moodle.example/mod/forum/view.php?id=1", "course:X")
    assert {f.field for f in facts} == {"course", "title", "coverage", "source_timestamps"}
    assert not any("unread" in str(f.value) or "mark=read" in str(f.value) for f in facts)
    assert all(f.external_ref.endswith("d=12") for f in facts)
