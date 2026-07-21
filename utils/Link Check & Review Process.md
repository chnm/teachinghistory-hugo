# Link Check & Review Process

> **Tooling status (2026-07-21):** Steps 1 and 1.5 below are now automated by
> `utils/link_checker.py` (see the repo-root `CLAUDE.md`, "External Link
> Checker"). The deliverables for team review are `utils/link_review_master.xlsx`
> (one row per link, incl. auto-triaged "Rebranded"/C-candidate verdicts) and
> `utils/link_review_pages.xlsx` (one row per page, for bulk delete/salvage
> calls). Record decisions in each sheet's `decision` dropdown column — nothing
> touches content until the sheets are approved and a (future) apply step runs.
> Steps 2–4 remain human judgment, informed by the sheets.

# Step 1: Fix Link Checker

Best case scenario, the process of finding broken links is able to be automated. If not, it can be done by a human or a combination of human/automation.

Links should be marked “Broken” if **ANY** of the following:

1. The link does not deliver at all, nothing appears.  
   1. Example: ([https://hsi.wm.edu/cases/jamestown/jamestown\_preview.html](https://hsi.wm.edu/cases/jamestown/jamestown_preview.html)) from this THist page ([https://dev.teachinghistory.org/teaching-materials/lesson-plan-reviews/24214/](https://dev.teachinghistory.org/teaching-materials/lesson-plan-reviews/24214/))  
   2. Example: ([http://herb.ashp.cuny.edu/](http://herb.ashp.cuny.edu/)) from this THist page ([https://dev.teachinghistory.org/teaching-materials/lesson-plan-reviews/25185](https://dev.teachinghistory.org/teaching-materials/lesson-plan-reviews/25185))  
2. The link delivers to the correct site, but the wrong page.  
   1. Example: ([https://www.gilderlehrman.org/content/what-events-led-lincoln%E2%80%99s-assassination](https://www.gilderlehrman.org/content/what-events-led-lincoln%E2%80%99s-assassination)) This lesson plan still exists on the site, but at this new URL: [https://www.gilderlehrman.org/history-resources/lesson-plan/what-events-led-lincolns-assassination](https://www.gilderlehrman.org/history-resources/lesson-plan/what-events-led-lincolns-assassination)  
   2. Example: ([http://landmarkcases.org/en/landmark/home](http://landmarkcases.org/en/landmark/home)) This page still exists on the site, but at this new URL ([https://landmarkcases.org/cases/marbury-v-madison/](https://landmarkcases.org/cases/marbury-v-madison/))  
   3. Example ([https://www.thehenryford.org/education/resources/](https://www.thehenryford.org/education/resources/)) This site is correct, but the lesson does not actually exist anymore, as they have overhauled their education materials.  
3. The link delivers to *a* site, but not the correct one.  
   1. Example: Since Skype has been purchased by MS Teams, the link to [skype.com](http://skype.com) on this THist page ([https://dev.teachinghistory.org/digital-classroom/tech-for-teachers/23569/](https://dev.teachinghistory.org/digital-classroom/tech-for-teachers/23569/)) now delivers to ([https://teams.live.com/free](https://teams.live.com/free))  
   2. Example: various inappropriate sites  
   3. Example: Since this project has been rebranded or purchased, the link to [wallwisher.com/](http://wallwisher.com/) on this THist page ([https://dev.teachinghistory.org/digital-classroom/tech-for-teachers/24636/](https://dev.teachinghistory.org/digital-classroom/tech-for-teachers/24636/)) now delivers to ([https://padlet.com/](https://padlet.com/))  
4. The link delivers to the correct site and the correct page, but the project is either shut down or does not work anymore. These would either be eligible for WayBack or have to be removed.  
   1. Example: There are lots of links to this project that don’t work. It appears to be a defunded NEH project ([http://edsitement.neh.gov/lesson-plan/my-piece-history\#sect-activities](http://edsitement.neh.gov/lesson-plan/my-piece-history#sect-activities)) and now redirects to this URL ([https://www.neh.gov/project/edsitement\#sect-activities](https://www.neh.gov/project/edsitement#sect-activities)) which doesn’t actually let you access the project. This would be a good candidate for Wayback.  
   2. Example: ([https://www.nj.gov/state/njhistorypartnership/](https://www.nj.gov/state/njhistorypartnership/)) this link technically delivers, but the project doesn’t work anymore. 

## Step 1.5: Run New Checker (automated or human)

Of the Broken links, there may be some we can eliminate in bulk before going through the more scrutinizing process of deciding to remove or salvage. After running the link checking system, we should identify these links that can be removed in batches (removing hyperlinks on text or removing written out urls).

### Batch/Bulk Deletion

If broken links appear in **ANY** of the following sections of a piece of content on Teaching History, it should be deleted/unlinked/removed at this point:

* Bibliography, Further Reading, References- These sections at the bottom of the posts give citations for what was written, the links are not as essential as the actual reference information (author, date, repository, etc…).  
  * Example: ([https://dev.teachinghistory.org/history-content/ask-a-historian/24451/](https://dev.teachinghistory.org/history-content/ask-a-historian/24451/)) If any links in the bottom section of this post were broken (below the line divider and/or under “For Further Reading”), they could be deleted inconsequentially because the reference information would remain.  
* Caption under a photo or source- These are also probably citations. Reference information should be kept, but links are not essential information here.  
  * Example: This teaching guide is full of citation links ([https://dev.teachinghistory.org/teaching-materials/teaching-guides/25882/](https://dev.teachinghistory.org/teaching-materials/teaching-guides/25882/)). Some are more necessary than others. The extension videos links are necessary to keep for function, but links like “March to Wounded Knee: Earth Day World Pilgrimage Poster, 1973, Library of Congress, [https://www.loc.gov/item/2016648085/](https://www.loc.gov/item/2016648085/)” could just be deleted if they were broken because the title/date/repository would remain (I think they are fine, just illustrating my point).  
* Amazon, B\&N, Press websites, and other links out to promote book/material sales- this might be identified by the text of the url, but also might be identified by the context of the sentence the link was put in.  
  * Example: In this post ([https://dev.teachinghistory.org/teaching-materials/ask-a-master-teacher/24483](https://dev.teachinghistory.org/teaching-materials/ask-a-master-teacher/24483)) the second to last paragraph says “National Geographic’s Illustrated Time Line or John Teeple’s Timelines of World History are books for purchase…” and links out to where one might buy those two books (amazon). Those links are broken and because they are just leading to purchase portals, they can be sorted into the batch delete pile.

# Step 2: Remove or Salvage (Round 1\)

### Try to salvage IF **any** of the following:

* Broken B, especially if the original link is to a site that is [Wayback Machine Eligible](#wayback-machine-eligible-sites)  
* Broken C or D, **only** if the original link is to a site that is [Wayback Machine Eligible](#wayback-machine-eligible-sites)

### Remove IF **any** of the following:

* Broken C or D, and the original link is **NOT** [Wayback Machine Eligible](#wayback-machine-eligible-sites)  
* Broken A

# Step 3: Remove or Salvage (Round 2\)

Once we have identified what is broken and what can be salvaged, we must decide what we want to salvage (what would be useful to salvage).

### Salvage (As Is) if **ALL** of the following:

* The Wayback machine fix would work or there is an updated link that could be found and put in place. See [Looking For a New Link](#looking-for-a-new-link).  
* Written content is good. See [Subjective Review](#subjective-review).

### Salvage (Update or Change) if **ANY** of the following:

* The Wayback machine fix would work or there is an updated link that could be found and put in place. See [Looking For a New Link](#looking-for-a-new-link).  
* Written content is good, but doesn’t need to link to specific external links, could be done more conceptually, or could be combined more usefully with other content. See [Subjective Review](#subjective-review).

### Remove if **ANY** of the following:

* Attempts to salvage the link(s) fail  
* Written content is insufficient in some way. See [Subjective Review](#subjective-review).

# Step 4: Enact Solutions

By this step, we have determined what is broken, what might be fixed with technical means, what might be fixed with subjective means, what could be worth the time and energy to fix/salvage, and what subjective solutions might be most useful. This step is when you will enact the solutions that have been approved by the team after your thorough technical and subjective reviews.

Since subjective solutions entail more of a time commitment and intellectual effort, they should be proposed, discussed, and approved as a team before moving forward.

Salvaging will mean different things for different kinds of content and will involve both technical and subjective solutions. The following solution ideas assume that for each category, we have gone through Steps 1-3, fixed anything that can be fixed technically, and made a recommendation based on   
These solutions are to build out the Salvage (Update or Change) recommendations…. Or is it that i want this to be supplement to the subjective review? I’m realizing that a lot of what I’m putting here is covered in the subjective review… should this just be a placet put special considerations  
**\* \= IF we have the manpower to consider/do this.**

### 

# Wayback Machine Eligible Sites {#wayback-machine-eligible-sites}

* Any project funded by the National Endowment for the Humanities (NEH)  
* National Park Service  
* The United States Holocaust Memorial Museum

# Looking For a New Link {#looking-for-a-new-link}

If the link is Broken B (it delivers to the right site, but the page is wrong), you may be able to find a new link that does work. Sometimes when websites update or change, the materials sometimes get new links and our links stop working.  
**Test if this is the case:**

* If the website has a search function, search the title (in quotes, and then out of quotes if necessary) to find the material.  
* Google the title (in quotes) and the site (also in quotes). This may only yield other outside links to the same thing.

If you find a new link, notate that in your links sheet \[insert link tk\].  
If you cannot find a new link (the material has just been deleted), mark the THist content/link recommendation as “Remove” on your sheet.

# Subjective Review {#subjective-review}

Once a link has been marked as Broken in some way and you have determined that it is technically salvageable (with the Wayback or a new link), Subjective Review is necessary to determine how useful it would be to salvage the content. Since subjective solutions entail more of a time commitment and intellectual effort, they should be proposed, discussed, and approved as a team before moving forward. After moving through the series of questions and prompts that follow–including category specific considerations–make a recommendation (Remove, Salvage (As Is), Salvage (Update or Change)) and explain.

1. What category does this content fall under? (ex: Tech for Teachers, Teaching Guides, Blog, etc…) How many total posts are in that category?  
2. When was this post written?  
3. Does this post match the style of other posts in this category?  
4. If making a tech recommendation or review, does that technology still exist? Is it still widely used by educators? Is there something better or comparable?  
5. Are the outward links essential? For example, are the broken links to primary sources (which could be deleted while keeping the rest of the citation), or are the broken links to something more essential (like for a Website Review post or a video)? Is there a way to redo this post without external links?  
6. Is there another place/post on Teaching History that covers this topic? If so, how are the posts similar and different? Does it make sense for them to be split?  
7. What are you curious about after reading the post?  
8. Are there other posts in this category that cover similar topics? Could they be synthesized? For example, multiple posts on different mapping softwares could be re-written as a single post about using maps and mapping in the classroom with little to no specific tech recommendations.  
   1. Even if there are no similar posts, is there a way to rewrite this post in a more conceptual way that would be more useful for teachers?  
9. Do some research on the topic (Reddit is a great source of teacher community and conversation). What is the post missing? What innovations have been made in recent years? What are some current challenges being faced by teachers in this area that we can help address? What are some ways teachers are engaging with this topic or thing that seem successful?  
10. Do some benchmarking. Look at other websites for teachers. Is this content in line with what others are providing/searching for?  
11. **Overall,** is this content that Teaching History should invest time and money into maintaining? 

## Content-Specific Solution Ideas and Considerations

The following notes on specific content categories should be used as additional guiding questions and processes when doing the in-depth Subjective Review. That is, these solutions are not meant to replace the Subjective Review, nor do they have to be enacted for every piece of content. Instead, they are things to consider when reviewing content that is specific to the mission of each type of post.  
**\* \= IF we have the manpower to consider/do this.**

### Tech for Teachers

* The two main goals for editing and improving this category on the website are:

  1\. Removing posts about things that are no longer relevant (ex: Skype, Jamboard)

  2\. Rewriting things to be more conceptual (this gets rid of specific tech recommendations that might become outdated and minimizes external linking).

* **\*** Use Claude to do a small scale topic model to determine if there are multiple posts that have similar content. If yes, consider how they may be rewritten more cohesively about a general concept rather than specific technology recommendations. Ex: using collaborative/interactive technology in the classroom rather than recommending specific digital whiteboard platforms.

### Blog, Ask a (Educator, Historian, Digital Historian)

* The main goals for editing and improving these four categories of content are:

  1\. Removing posts about things that are no longer relevant (ex: Skype, Jamboard)

  2\. Reducing the number of posts in these categories to a manageable number

  3\. Ensuring the same thing isn’t discussed across multiple posts–and if this must happen, that the posts very explicitly connect to one another.

* Jjj

### ELL

* Make sure content is up to date either by finding resources geared towards English Language Learning educators or by sending this content to an ELL educator who can review it.  
* Consider requesting content new from subject matter experts.

### Teaching Guides

* The main goal for editing and improving this category of content is making sure that all the content is serving the same designated purpose:

**When making your recommendation, be sure to thoroughly record your thoughts and reasoning. Specifically engage with the questions and prompts above, but also any additional notes you take.**  
