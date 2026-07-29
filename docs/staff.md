# Managing Staff

Staff members are stored as structured data in `teachinghistory-website/data/staff.yaml` and rendered on the `/about/staff/` page using `layouts/about/staff.html`.

## File location

```
teachinghistory-website/data/staff.yaml
```

## Structure

Staff are organized into groups. Each group has a `name` and a list of `members`:

```yaml
groups:
  - name: Leadership and Content Team
    members:
      - name: Kelly Schrum
        role: Director and PI
        bio: >
          Director of Educational Projects at CHNM...
```

Each member has three fields:

| Field  | Required | Description                        |
|--------|----------|------------------------------------|
| `name` | Yes      | Full name                          |
| `role` | Yes      | Job title or role                  |
| `bio`  | Yes      | Biography text (plain text, no Markdown) |

## Adding a new staff member

1. Open `teachinghistory-website/data/staff.yaml`
2. Find the appropriate group (Leadership and Content Team, Web Design and Development, or Alumni)
3. Add a new entry under `members`:

```yaml
      - name: Jane Doe
        role: Research Associate
        bio: >
          Jane Doe is a researcher specializing in American history.
          She holds a PhD from Example University.
```

4. Use `>` (folded scalar) for multi-sentence bios so line breaks in the YAML become spaces in the output.

## Moving a staff member to Alumni

1. Cut the member entry from their current group
2. Paste it under the `Alumni` group
3. Update their `role` to reflect their former position (e.g., "Former Research Associate")

## Adding a new group

Add a new entry at the top level of `groups`:

```yaml
  - name: New Group Name
    members:
      - name: ...
```

The groups render in the order they appear in the YAML file.

## Layout

The staff page uses a two-column grid. Each card shows the name, role (in orange), and a "Read Bio" link. Clicking "Read Bio" opens a modal dialog with the full biography.

The layout file is `teachinghistory-website/layouts/about/staff.html`.
