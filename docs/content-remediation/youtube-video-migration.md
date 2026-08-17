# YouTube video migration

This workflow uploads the 87 videos required by current Hugo pages, records
every returned YouTube ID, and then converts all 287 current Hugo video entries
from local MP4 sources to YouTube embeds.

The uploader is deliberately gated:

- New manifest rows are unapproved and default to `unlisted`.
- No upload occurs without an approved row and `--confirm-upload`.
- State is saved after every completed upload so interrupted runs are safe to
  resume and do not duplicate finished work.
- The Hugo migration refuses to write until all 287 current clips have IDs.

## 1. Google and channel setup

1. Select or create a Google Cloud project owned by the organization.
2. Enable **YouTube Data API v3**.
3. Confirm that the project is approved for public or unlisted API uploads.
   Projects created after July 28, 2020 that have not passed YouTube's API
   compliance audit are restricted to private uploads.
4. Create an OAuth 2.0 **Desktop app** client and download its client JSON.
5. A manager of the TeachingHistory YouTube channel must complete the first
   browser authorization.

The uploader is pinned to the existing `teachinghistoryorg` channel ID
`UCZBG3EdPK_3O8oUkEE40ZsQ` and refuses to upload to a different authenticated
channel.

Store the client JSON and generated token outside the repository, for example:

```text
~/.config/teachinghistory-youtube/client-secret.json
~/.config/teachinghistory-youtube/token.json
```

Official references:

- <https://developers.google.com/youtube/v3/guides/uploading_a_video>
- <https://developers.google.com/youtube/v3/docs/videos/insert>
- <https://developers.google.com/youtube/v3/guides/quota_and_compliance_audits>

## 2. Python setup

From the repository root:

```sh
uv venv
uv pip install -r utils/youtube-requirements.txt
```

The OAuth client secret, OAuth token, generated manifests, and upload state are
local operational data and must not be committed.

Authorize and verify the channel before preparing the batch:

```sh
.venv/bin/python utils/youtube_migration.py auth-check \
  --client-secrets ~/.config/teachinghistory-youtube/client-secret.json \
  --token-file ~/.config/teachinghistory-youtube/token.json
```

The command must report `matches_expected_channel: true`.

## 3. Source-video access

The server inventory identifies the source directory as:

```text
/var/www/html/web/sites/default/files/media/video/
```

The upload command must run on a machine where this directory is available, or
against a read-only mounted/copied version of it. The inventory comment confirms
matching filenames, but `validate` performs the authoritative preflight against
the actual files before any upload.

## 4. Generate and review metadata

```sh
.venv/bin/python utils/youtube_migration.py manifest
.venv/bin/python utils/youtube_migration.py validate
```

Review `outputs/youtube-migration/youtube-upload-review.xlsx`. Titles follow the
existing channel patterns, descriptions use the Hugo summary plus the canonical
TeachingHistory URL, the category is Education, and the legacy asset name is
used as the tag. Titles over 100 characters are shortened and flagged for review.

`outputs/youtube-migration/server-source-files.txt` is the exact 87-file list a
sysadmin can use to stage only the immediate upload batch instead of copying the
entire server inventory.

Set `approved` to `Yes` only after reviewing a row. Export the **Upload Manifest**
sheet as:

```text
outputs/youtube-migration/upload-manifest.csv
```

Then verify the real server files:

```sh
.venv/bin/python utils/youtube_migration.py validate \
  --video-root /var/www/html/web/sites/default/files/media/video
```

## 5. Upload two canaries

Approve two representative rows, then run:

```sh
.venv/bin/python utils/youtube_migration.py upload \
  --video-root /var/www/html/web/sites/default/files/media/video \
  --client-secrets ~/.config/teachinghistory-youtube/client-secret.json \
  --token-file ~/.config/teachinghistory-youtube/token.json \
  --max-uploads 2 \
  --confirm-upload
```

Inspect the resulting unlisted videos in YouTube Studio. Check the correct media,
title, description, category, channel, visibility, and playback.

The existing channel contains mixed license settings. The uploader intentionally
does not override YouTube's standard license default until the team chooses a
single license policy.

## 6. Complete the approved batch

After approving the remaining rows and validating the canaries:

```sh
.venv/bin/python utils/youtube_migration.py upload \
  --video-root /var/www/html/web/sites/default/files/media/video \
  --client-secrets ~/.config/teachinghistory-youtube/client-secret.json \
  --token-file ~/.config/teachinghistory-youtube/token.json \
  --confirm-upload
```

The current YouTube Data API default is 100 `videos.insert` calls per day, so the
87-video immediate queue fits within one default daily upload bucket. Channel
limits or processing delays can still interrupt a run; re-run the same command
and the checkpoint file will skip completed uploads.

## 7. Convert Hugo to YouTube IDs

Generate the combined plan. It uses 200 existing matches plus the 87 IDs returned
by the uploader:

```sh
.venv/bin/python utils/youtube_migration.py hugo-plan
```

Run the content migration in dry-run mode first:

```sh
.venv/bin/python utils/youtube_migration.py apply-hugo
```

The command refuses to proceed while any current Hugo video lacks a YouTube ID.
Once the dry run reports 287 complete clips, apply it:

```sh
.venv/bin/python utils/youtube_migration.py apply-hugo --confirm-apply
```

This replaces `src` in each page's `videos` frontmatter with `youtube_id` while
preserving the existing thumbnail and title. The Hugo player uses
`youtube-nocookie.com` embeds and retains the thumbnail-driven clip selector.

Finally:

```sh
just build
just check
```

Visually verify several single- and multi-clip pages before committing and
opening the pull request.
