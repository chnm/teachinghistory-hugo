The first thing I started on with the glorious sheet of broken links was the section of 500 broken links marked as “Rebranded.” I did a sampling of the 500 and found that this mechanism of the Claude sweep worked extremely well. It did catch quite a few urls successfully migrating to the same content that just had a new url, but these “false” broken markers are worth it to us because it means Claude is being thorough. A link being successfully Rebranded or moved also signalled to us that the resource is something the external group has continued to invest in and so then should we. Reducing bulk around these still relevant resources and making sure our site is functioning properly to connect to them should be a priority.
SO, the two main questions that emerged from this finding were: how can we determine which Rebranded links are actually a problem and which of those problem links do we want to fix?

A couple of patterns did emerge among the actually broken rebranded links that have got us thinking about potential solutions:

1. Redirects to home pages (Ex: a news article link now goes to the home page of that news site, some chnm content links just go to rrchnm.org now).

2. There was the occasional inappropriate site (Ex: Primary Access, once a primary source page is now a Vietnamese gambling website).

Given these two patterns and a desire to efficiently determine real problems, we are proposing this idea of how we might make the “human should look at it” definition a bit more tight:

• Prompting Claude to determine if the Final URL looks like a homepage (probably by looking at the final url text- does it have a slug?).
• Prompting Claude to evaluate whether a site looks like a history site with very specific criteria/vocabulary like, does it include words from this list: primary sources, history, education, museum, etc.
• THEN, for these 500 Rebranded links, we could have this be the computed logic:.
◦ If the final url is probably NOT a homepage, and it DOES appear to probably be a history website, Claude can mark it as probably fine and not in need of a human eye..
◦ If the final url is probably NOT a homepage, and it does NOT look like a history website, then a human should look at it..

The second question (which of the problem links do we want to fix) can apply to Rebranded links, but also to the rest of the links in the sheet. Hoping to be conservative with what things to spend time fixing, we were ideating a way to decide in bulk if certain pages should just be deleted entirely (rather than having links deleted or edited). For example, if a Website Review or National Resources page has a broken link that cannot be fixed, there is really nothing of value left on that page, and so the page should just be deleted. Alternatively, something like a teaching guide would probably be fine with one or a few unfixable/deleted links because links (external resources) are not the central element.

With this question and these considerations in mind, we are proposing:

• Prompting Claude to take the broken links sheet and create a derivative sheet that shows every row as a unique page (rather than every row being a link and having potentially multiple rows that belong to the same page).

This would allow us to identify all at once every Website Review and National Resource page with broken links and decide to delete them all (provided their broken links are not candidates for WayBack)
