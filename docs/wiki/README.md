# Wiki source

These pages are the source of the GitHub wiki
(`https://github.com/fiwon123/ai-youtube-video-workflow/wiki`). They live in the repository so a
change to them is reviewed like any other, and so the wiki cannot drift from the
release it describes.

## Publishing

The wiki is a second git repository. GitHub creates it the first time a page is
saved in the web UI (once, by hand: Wiki tab → *Create the first page*). After
that, publish with:

```bash
make wiki-push
```

It mirrors this folder into the wiki — every page here except this README —
so a page deleted here disappears there, and an edit made in the web UI is
overwritten. Change the pages here, through a pull request.

The file names are the page names: `Home.md` is the landing page, `_Sidebar.md`
is the navigation.

> **Note:** CI does not publish the wiki; `make wiki-push` is run by a person.
