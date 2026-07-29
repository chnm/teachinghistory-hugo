# Summary of Findings

1. The Dev site transfer seems to have only transferred content in the main frame of the page (not the margins). When creating content on the drupal site, things are put into different fields that together construct a page. The Dev site transfer seems to have only transferred content within Drupal’s “Article Body” field. This means that information placed in other fields when constructing pages on the Drupal site–including author bio/information, thumbnail or “splash” images, links to related pages, and, in some cases, tables of contents– was not carried over to the new site.  
   * Example 1:  
     * Original/Drupal site: [teachinghistory.org/teaching-materials/lesson-plan-reviews/25867 ![][image1]](https://teachinghistory.org/teaching-materials/lesson-plan-reviews/25867)  
     * Dev site: [https://dev.teachinghistory.org/teaching-materials/lesson-plan-reviews/25867/](https://dev.teachinghistory.org/teaching-materials/lesson-plan-reviews/25867/)

     ![][image2]

   * Example 2:  
     * Drupal Site: The Annotations and Mini-Writes Teaching guide has an image in the “image,” splash, and thumbnail fields. None of which appear on the dev site. [https://teachinghistory.org/teaching-materials/teaching-guides/23554](https://teachinghistory.org/teaching-materials/teaching-guides/23554)  
       ![][image3]  
     * Dev Site: [https://dev.teachinghistory.org/teaching-materials/teaching-guides/23554/](https://dev.teachinghistory.org/teaching-materials/teaching-guides/23554/)   
       ![][image4]

2. Even images placed in the “Article Body” field of Drupal pages did not transfer over to the dev site. As stated above, images in other Drupal fields do not transfer at all to the dev site. However, several pages had images embedded within the “Article Body.” While the images themselves have not transferred, the “containers” for these images have. On the Dev site, they appear as blank spots with captions.  
   * Example:  
     * Drupal site: [https://teachinghistory.org/teaching-materials/teaching-guides/25882](https://teachinghistory.org/teaching-materials/teaching-guides/25882)  
        ![][image5]  
   * Dev Site: [https://dev.teachinghistory.org/teaching-materials/teaching-guides/25882/](https://dev.teachinghistory.org/teaching-materials/teaching-guides/25882/) ![][image6]  
3. There is some mismatch and faulty transfer because many pages were not properly or completely deleted from the backend of the Drupal site. This manifests in 2 different ways: 1\) the page exists on the Dev site and is not blank, but on the Drupal site, the page is blank to viewers (though it does still exist on the backend); 2\) the page exists on the Dev site but is blank, and on the Drupal site, the page is blank to users (though it does exist on the backend). It is not currently clear why the Dev site hasn’t transferred them all consistently.  
   * Example 1: Enews  
     * Dev Site: “March 2010”. Exists as a page but is blank. [https://dev.teachinghistory.org/enews/march-2010-24509/](https://dev.teachinghistory.org/enews/march-2010-24509/)![][image7]  
     * Drupal Site: is blank to users but exists on the backend. [https://teachinghistory.org/node/24509](https://teachinghistory.org/node/24509)![][image8]  
       ![][image9]  
   * Example 2: Research-Briefs  
     * Dev Site: “Discussing Controversial Public Issues in the Classroom”. It does appear. [https://dev.teachinghistory.org/research-brief/discussing-controversial-public-issues-in-the-classroom-25748/](https://dev.teachinghistory.org/research-brief/discussing-controversial-public-issues-in-the-classroom-25748/)  
       ![][image10]  
     * Drupal Site: is blank to users but exists on the backend. [https://teachinghistory.org/search/node?keys=Discussing%20Controversial%20Public%20Issues%20in%20the%20Classroom](https://teachinghistory.org/search/node?keys=Discussing%20Controversial%20Public%20Issues%20in%20the%20Classroom)![][image11]  
       ![][image12]

## Notes Split into 2 Priority Streams

### Top Priority List (things not working on the Dev site that should be):

* *Transferred Twice*  
  * Beyond the Textbooks section transferred twice. However, while pages in Beyond-the-Textbook-Part-2s are visible on the Dev site, the other ones (Beyond-the-Textbook) are all blank. Should just delete that one and rename the other.  
* *Did Not Transfer to Dev*  
  * **Pages that are visible on Drupal, but not on Dev:**  
    * Beyond-the-Chalkboards: From spot checking, it seems that these are NOT populating in the dev site. These DO appear on the original site.  
      * Example: dev ([https://dev.teachinghistory.org/digital-classroom/beyond-the-chalkboard/24152/](https://dev.teachinghistory.org/digital-classroom/beyond-the-chalkboard/24152/)) original: ([https://teachinghistory.org/digital-classroom/beyond-the-chalkboard/24152](https://teachinghistory.org/digital-classroom/beyond-the-chalkboard/24152))  
    * Quizlies: Accessible on Drupal through the name [History Quiz](https://teachinghistory.org/history-content/quiz) on History Content Content is blank on the dev. 124 resources.   
    * Research-Tools: accessible from Digital Classrooms \- called [Tech for Teachers](https://teachinghistory.org/digital-classroom/tech-for-teachers). Content is blank on the dev, 72 blank resources.   
    * Websites, called Website Reviews and accessible through History Content. Visible on the original website but not on the dev site. Content will need to be reviewed. [https://teachinghistory.org/history-content/website-reviews/25144](https://teachinghistory.org/history-content/website-reviews/25144)  [https://dev.teachinghistory.org/history-content/website-reviews/25144/](https://dev.teachinghistory.org/history-content/website-reviews/25144/)   
    * Press-Releases: In the about section and accessible from the footer. Content is visible on the original. Content of the original includes links to content that is no longer on Drupal.  Blank on the dev.   
    * Teaching-Guides-Prototype-Gens \- Blank on the Dev site. (unsure about if this was supposed to remain on the original) Can be found through searching but I am not sure how to access it in any other way.[https://teachinghistory.org/search/node?keys=Visiting%20History%3A%20A%20Professional%20Development%20Guide](https://teachinghistory.org/search/node?keys=Visiting%20History%3A%20A%20Professional%20Development%20Guide)   
    * Teaching-Guides-Prototype-Gen-Ches: (unsure about if this was supposed to remain on the original) Blank on the dev site. I found these resources through searching and by looking on the referenced webpage [https://teachinghistory.org/visiting-history](https://teachinghistory.org/visiting-history) on the original website.   
    * Teaching-Guides-Prototype-Children: (Unsure about if this was supposed to remain on the original) Can be found while searching, and leads to a page with content on the original, but blank on the Dev site I am not sure if it is accessible any other way because it looks like the original container that held it on the webpage was deleted. These also do not seem like stand alone or complete pages, like they were linked to something else. [https://teachinghistory.org/search/node?keys=Using+Historical+Footage+%28High+School%29](https://teachinghistory.org/search/node?keys=Using+Historical+Footage+%28High+School%29)  
    * Elementary/Middle/High-Quick-Links: For all three. Blank on the dev site probably because it is blank when navigating to it 1 of 2 ways on the Drupal site. It is blank when finding it through SEARCH but appears when clicking the link at the bottom of the page. Found through clicking ([https://teachinghistory.org/quick-links-elementary](https://teachinghistory.org/quick-links-elementary)), Found through search ([https://teachinghistory.org/node/24283](https://teachinghistory.org/node/24283))  
    * English-Language-Learners: These are blank on the dev site, but available on the original site. Can be found on the original site through search and by navigating several steps through Teaching Materials\>[ELL](https://teachinghistory.org/teaching-materials/english-language-learners)\>From the Classroom Example:[https://dev.teachinghistory.org/teaching-materials/english-language-learners/24129/](https://dev.teachinghistory.org/teaching-materials/english-language-learners/24129/) vs [https://teachinghistory.org/teaching-materials/english-language-learners/24129](https://teachinghistory.org/teaching-materials/english-language-learners/24129)  
    * Ex-of-Historical-Thinkings: Blank on the dev site, but accessible on the original site. Example: [https://teachinghistory.org/best-practices/examples-of-historical-thinking/25846](https://teachinghistory.org/best-practices/examples-of-historical-thinking/25846) ; [https://dev.teachinghistory.org/best-practices/examples-of-historical-thinking/25846/](https://dev.teachinghistory.org/best-practices/examples-of-historical-thinking/25846/)  
    * Examples-of-Teachings: Some of these are blank on the dev site but NOT all. Example (visible on dev): [https://dev.teachinghistory.org/best-practices/teaching-in-action/14947/](https://dev.teachinghistory.org/best-practices/teaching-in-action/14947/) [https://teachinghistory.org/best-practices/teaching-in-action/14947](https://teachinghistory.org/best-practices/teaching-in-action/14947) Example (not visible on dev, but yes visible on original): [https://dev.teachinghistory.org/best-practices/teaching-in-action/23724/](https://dev.teachinghistory.org/best-practices/teaching-in-action/23724/) [https://teachinghistory.org/best-practices/teaching-in-action/23724](https://teachinghistory.org/best-practices/teaching-in-action/23724)  
  * **Did not transfer completely to the Dev (Ex. margins absent, images absent)**  
    * Teaching-With-Textbooks: Visible on the dev and original website, margins did not copy over.  
    * Teaching-Guides: Accessible from teaching materials. Teaching Guides \- 43 resources visible on the original website, only 39 resources on the dev under this header the most recent four do not seem to have transferred over.   
    * Primary-Source-Guides \- Transferred over without the margins. Some of the embed videos no longer work on the original, dead links.  
    * National-Resource-Centers: The margins did not transfer over.  
    * Blogs: Missing margin content.  
    * Pages \- This section has 99 resources, including landing pages for various content types I believe (Teaching materials.) and some if not all of the about pages. Some are blank, and some are visible on one or both of the websites. Will probably need to go through and see what should be deleted and what should not be deleted. Examples: [https://teachinghistory.org/node/25738](https://teachinghistory.org/node/25738) , [https://teachinghistory.org/node/25725](https://teachinghistory.org/node/25725)  
      * Another Example: Dev: Only Some of the content transferred over   
      * Dev:[https://dev.teachinghistory.org/page/interactive-historical-thinking-poster-secondary-25630/](https://dev.teachinghistory.org/page/interactive-historical-thinking-poster-secondary-25630/)   
      * Two versions of the page on the original, one with content and one without, Without content: [https://teachinghistory.org/node/25630](https://teachinghistory.org/node/25630) With Content: [https://teachinghistory.org/historical-thinking-poster-2](https://teachinghistory.org/historical-thinking-poster-2) under print materials accessible under outreach-print materials

### Second Priority List (things to consider changing once Dev site is functional):

* *Delete From Dev Site*  
  * **Pages that are not visible on Drupal, but were transferred to Dev:**  
    * Annual-Report-States: Not visible on original teaching history site. If searching individual states, a result pops up in the search but when clicking on it, there is no visible content  
      * Example: [https://teachinghistory.org/search/node?keys=Vermont](https://teachinghistory.org/search/node?keys=Vermont)  
    * Annual-Reports: The original document is not visible on the original site. There is an “updated” page that is available. does not look like it is accessible besides searching.   
      * [https://teachinghistory.org/search/node?keys=Report%20on%20the%20State%20of%20History%20Education](https://teachinghistory.org/search/node?keys=Report%20on%20the%20State%20of%20History%20Education)  
    * Research-Briefs: Could not find these materials on orig site but Content is on the Dev. Ex. [https://teachinghistory.org/search/node?keys=Discussing%20Controversial%20Public%20Issues%20in%20the%20Classroom](https://teachinghistory.org/search/node?keys=Discussing%20Controversial%20Public%20Issues%20in%20the%20Classroom)   
    * Roundtable-Responses: Not accessible on the website but the record still comes up when searching the website.  Content available on the dev.  
    * Roundtables: Not accessible on the website but the record still comes up when searching the website. Content is blank on the dev.  
    * Tah-Directors-Conference-Days: Not accessible on the website but still comes up when searching the website. Content is blank on the dev.  
    * Tah-Directors-Conferences: Not accessible on the website but still comes up when searching the website. Content is blank on the dev.   
    * Tah-Grants: Not accessible on the original website but still comes up when searching the website. Content is blank on the dev.   
    * Teaching-Standards: No longer accessible to the public on the original site but still comes up when you search for content. Is accessible on the Dev site.   
    * Webforms Not visible on the dev or the original website.  
    * Workshops-and-Lectures no longer accessible on the original website  
    * Teaching-Guides-Prototypes (not sure). Blank on the original and Blank on the Dev site. Is linked on two visible content pages on the original site. [https://teachinghistory.org/search/node?keys=%22Teaching%20with%20Historical%20Film%20Clips%22](https://teachinghistory.org/search/node?keys=%22Teaching%20with%20Historical%20Film%20Clips%22)  
    * Enews: These are all blank pages on the dev site AND mostly gone from the Drupal site. When searching “Enews” on the original site, only 3 pages populate but are out of date and seemingly broken pages from 10+ years ago. The rest of the pages do not appear to even be listed on the original site. Example: [https://teachinghistory.org/search/node?keys=Enews](https://teachinghistory.org/search/node?keys=Enews)  
    * Historical-Sites: Not visible on the dev site, also potentially missing from the original site, although they appear in the search results. possibly links that are integrated into other webpages \- [https://teachinghistory.org/search/node?keys=International+Spy+Museum](https://teachinghistory.org/search/node?keys=International+Spy+Museum) Example:[https://dev.teachinghistory.org/historical-site/mann-house-mi-22035/](https://dev.teachinghistory.org/historical-site/mann-house-mi-22035/) [https://teachinghistory.org/node/22035](https://teachinghistory.org/node/22035) Not clear what this content was for?  
    * History-in-Multimedia: Blank on BOTH dev site and original site. Guessing that these were also resources that are tied or were tied to other pages, maybe multimedia objects displayed on those other pages. Edit: Found at least one page of the resources here \- [https://teachinghistory.org/category/topic/international-relations?page=48](https://teachinghistory.org/category/topic/international-relations?page=48). I suspect the other pages list other resources from this category. Not clear what this content was for or if it was a standalone page or meant to be linked to something else.  
    * Lessons-Learneds: Some are blank on dev site but some are not. The ones that are blank on the dev site are blank on the original site as well.  
* *Check In-Page Functionality:*  
  * **Links etc…**  
    * Blogs: These may need to be deleted/updated for content BUT also these may include dead links [https://teachinghistory.org/nhec-blog](https://teachinghistory.org/nhec-blog).  
    * Ex-of-Historical-Thinkings: should check links and video functionality.  
    * Primary-Source-Guides  \- some of the embedded video links no longer work on the original.  
    * Lesson-Plan-Reviews  
* *Typos/Small Word Changes:*  
  * **Header Names:**  
    * Ask-a-Digital-Historians, Ask-a-Historians, Ask-an-Educators: On the Drupal site, these are all singular rather than plural.

# Other Notes About Content and Content Organization: 

* Much of the content from the digital classroom might be outdated and could either be removed or reorganized into the other major content areas?   
* Website reviews, and National Historic Sites will probably also require extensive review   
* What type of content is featured under blogs? This content area also seems like it will require some review.    
* Does there need to be separate guides for middle, elementary and high (quick lines) or can this be integrated into other pages maybe as a search filter.  
*  Do the “ask a” sections have to be separate pages? Another option is one page with a search filter.   
* How does the ALSO OF INTEREST section work, it seems to only pull from content of interest in the larger subcategory (History Content) the resource is found in, could it pull from content across the website.  
* Brainstorming organization:   
  * If this were to be more like World History Commons: some of the broader content areas could possibly fit categories on that site  
    * History Content (sources, some methods, resources & reviews maybe seperate)   
    * Teaching Materials (teaching)   
    * Best Practices (methods)  
    * Digital Classroom (teaching, methods)  
    * Blog (not sure the type of content \- combination or posts that function as guides compiling resources, blogs, news)  
    * Maybe include guides organizing content by subject or include a search filter that mirrors that.   
  * Less subcategories without the major content area (some replaced with search filters. \- more connections between content areas.   
* Broadly checking content will be kept on the new site to make sure it does not include links to content that is deleted.   
* Checking to see if multimedia items work. 

# Overall Notes- Comparing Dev and Original Site

**Gray Text \=** a page that is blank on the original/drupal site (lower priority)

Annual-Report-States:

* Not visible on the original teaching history site.   
* If searching individual states, a result pops up in the search but when clicking on it, there is no visible content  
* Example: [https://teachinghistory.org/search/node?keys=Vermont](https://teachinghistory.org/search/node?keys=Vermont)

Annual-Reports: 

* The original document is not visible on the original site. There is an “updated” page that is available. [https://teachinghistory.org/search/node?keys=Report%20on%20the%20State%20of%20History%20Education](https://teachinghistory.org/search/node?keys=Report%20on%20the%20State%20of%20History%20Education)  
* does not look like it is accessible besides searching. 

Ask-a-Digital-Historians:

* On the original site, it is “historian” rather than “historians”  
* Available on original site to click at the bottom of the page  
* Each page on the dev site under “Ask-a-Digital-Historian” comes up as an option on the original site.  
* The search function on the original site brings these up fine.  
* The content of each page appears on the old site with no issues.  
* Most if not all of these posts are outdated in terms of content.  
* Just from spot checking, it seems that the posts are populating in the dev site well with links but do not include images.  
* Can this be combined with the other ask a sections, with a search filter. 

Ask-a-Historians:

* On the original site, it is “historian” rather than “historians”  
* Same as above in terms of availability on the original teaching history site. It is accessible from the footer and the History Content page.   
* Can this be combined with the other ask a sections, with a search filter. 

Ask-an-Educators:

* On the original site, it is called “ask a master teacher” which should be changed.   
* Same as above in terms of availability on the original teaching history site. It is accessible from the footer and Teaching Materials.  
* Can this be combined with the other ask a sections, with a search filter.  

Beyond-the-Chalkboards:

* [Beyond the Chalkboards](https://teachinghistory.org/digital-classroom/beyond-the-chalkboard) is on the original site, but housed beneath the Digital Classroom page  
* These appear on the original site with search and by navigating through the Digital Classroom page.  
* From spot checking, it seems that these are NOT populating in the dev site. The pages I found to be blank DO appear on the original site.  
* Example: dev ([https://dev.teachinghistory.org/digital-classroom/beyond-the-chalkboard/24152/](https://dev.teachinghistory.org/digital-classroom/beyond-the-chalkboard/24152/)) original: ([https://teachinghistory.org/digital-classroom/beyond-the-chalkboard/24152](https://teachinghistory.org/digital-classroom/beyond-the-chalkboard/24152))  
* The embedded videos work, not sure about the content might be mostly outdated in terms of the tech they are using, not necessarily the process. 

Beyond-the-Textbook-Part-2s

* Beyond the Textbooks a section on the original site, but is housed beneath the History Content page  
* The pages on the dev site are not blank but are somewhat incomplete  
* Example: Girls’ Labor and Leisure is an essay that comes up twice when searching on the original site. 1\) a landing page of sorts for the essay with an abstract… you click to read the full essay; 2\) the full essay.[https://teachinghistory.org/history-content/beyond-the-textbook/25749](https://teachinghistory.org/history-content/beyond-the-textbook/25749)  
  * On the [dev version](https://dev.teachinghistory.org/history-content/beyond-the-textbook/25750/) of this essay, the content has transferred fine, but it is missing the table of contents, author information, and related items… seemingly everything in the margins of the original page.  
* None of the margins transferred over, incomplete transfer over the styling of the page. Most of the content links to things internal to the website instead of external websites.

Beyond-the-Textbooks:

* Same pages as the Part2 one above, but all of these versions of the pages on the dev site are blank.  
* Example: [https://dev.teachinghistory.org/history-content/beyond-the-textbook/25749/](https://dev.teachinghistory.org/history-content/beyond-the-textbook/25749/)

Blogs:

* From spot checking it seems that all of the pages have transferred over to dev from the original site (besides margin content)  
* On the original site, these pages are accessible through the blog linked on the home page, the navigation and through search  
* It is unclear to me what types of resources/content/information is included in this section of the website. Some of the information might also be out of date or include dead links \- [https://teachinghistory.org/nhec-blog](https://teachinghistory.org/nhec-blog). This might take a little work to transfer over. 

Elementary-Quick-Links:

* This is a single page on the dev site and is blank  
* [https://dev.teachinghistory.org/elementary-quick-links/quick-links-for-elementary-school-teachers-24283/](https://dev.teachinghistory.org/elementary-quick-links/quick-links-for-elementary-school-teachers-24283/)  
* Is also blank/nonexistant on original site when SEARCHING, but does pop up when clicking the link at the bottom of the page: Found through clicking ([https://teachinghistory.org/quick-links-elementary](https://teachinghistory.org/quick-links-elementary)), Found through search ([https://teachinghistory.org/node/24283](https://teachinghistory.org/node/24283))  
* Could this guide be a search filter instead of a separate page?

Enews:

* These are all blank pages on the dev site  
* When searching “Enews” on the original site, only 3 pages populate but are out of date and seemingly broken pages from 10+ years ago. The rest of the pages do not appear to even be listed on the original site  
* Example: [https://teachinghistory.org/search/node?keys=Enews](https://teachinghistory.org/search/node?keys=Enews)  
* Does not seem accessible from anyplace other than search.

English-Language-Learners: accessible from teaching materials

* These are blank on the dev site, but available on the original site.  
* Can be found on the original site through search and by navigating several steps through Teaching Materials\>[ELL](https://teachinghistory.org/teaching-materials/english-language-learners)\>From the Classroom  
* Example:[https://dev.teachinghistory.org/teaching-materials/english-language-learners/24129/](https://dev.teachinghistory.org/teaching-materials/english-language-learners/24129/) vs [https://teachinghistory.org/teaching-materials/english-language-learners/24129](https://teachinghistory.org/teaching-materials/english-language-learners/24129)  
* The landing page has a lot of content and is a bit confusing. The sub categories and how they are structured especially. 

Ex-of-Historical-Thinkings:

* Blank on the dev site, but accessible on the original site from Best practices or search through the name [Examples of Historical Thinking](https://teachinghistory.org/best-practices/examples-of-historical-thinking)  
* Example:  
  * [https://teachinghistory.org/best-practices/examples-of-historical-thinking/25846](https://teachinghistory.org/best-practices/examples-of-historical-thinking/25846)  
  * [https://dev.teachinghistory.org/best-practices/examples-of-historical-thinking/25846/](https://dev.teachinghistory.org/best-practices/examples-of-historical-thinking/25846/)  
* Not as many external links embedded in the content so less to check, and the videos work on the original site. 

Examples-of-Teachings:

* Some of these are blank on the dev site but NOT all.  
* Example (visible on dev): [https://dev.teachinghistory.org/best-practices/teaching-in-action/14947/](https://dev.teachinghistory.org/best-practices/teaching-in-action/14947/) [https://teachinghistory.org/best-practices/teaching-in-action/14947](https://teachinghistory.org/best-practices/teaching-in-action/14947)  
* Example (not visible on dev, but yes visible on original): [https://dev.teachinghistory.org/best-practices/teaching-in-action/23724/](https://dev.teachinghistory.org/best-practices/teaching-in-action/23724/) [https://teachinghistory.org/best-practices/teaching-in-action/23724](https://teachinghistory.org/best-practices/teaching-in-action/23724)  
* Accessible on the original site through search or from Best practices called [Teaching in Action](https://teachinghistory.org/best-practices/teaching-in-action).  
* Does not seem to include many external links so less to check, and most of the videos work on the original site. 

High-Quick-Links:

* Same as Elementary Quick Links. When clicking “Quick Links for High School Teachers” on the home page or the footer  of the original site, it appears BUT when searching, a link appears that leads to a blank page: [https://teachinghistory.org/node/24285](https://teachinghistory.org/node/24285)  
* Blank on the dev site: [https://dev.teachinghistory.org/high-quick-links/quick-links-for-high-school-teachers-24285/](https://dev.teachinghistory.org/high-quick-links/quick-links-for-high-school-teachers-24285/)  
* Could this guide be a search filter instead of a separate page?

Historical-Sites:

* Not visible on the dev site, also potentially missing from the original site, although they appear in the search results.  
* possibly links that are integrated into other webpages \- [https://teachinghistory.org/search/node?keys=International+Spy+Museum](https://teachinghistory.org/search/node?keys=International+Spy+Museum)  
* Example:[https://dev.teachinghistory.org/historical-site/mann-house-mi-22035/](https://dev.teachinghistory.org/historical-site/mann-house-mi-22035/) [https://teachinghistory.org/node/22035](https://teachinghistory.org/node/22035)  
* Not clear what this content was for?

History-in-Multimedia:

* Blank on BOTH dev site and original site  
* Guessing that these were also resources that are tied or were tied to other pages, maybe multimedia objects displayed on those other pages.  
  * Edit: Found at least one page of the resources here \- [https://teachinghistory.org/category/topic/international-relations?page=48](https://teachinghistory.org/category/topic/international-relations?page=48). I suspect the other pages list other resources from this category.  
* Not clear what this content was for or if it was a standalone page or meant to be linked to something else. 

Lesson-Plan-Reviews:

* Visible on dev site AND original  
* Accessible on original site from [teacher materials](https://teachinghistory.org/teaching-materials) and search  
* Some of the links do not work anymore. [https://teachinghistory.org/teaching-materials/lesson-plan-reviews/23941](https://teachinghistory.org/teaching-materials/lesson-plan-reviews/23941) 

Lessons-Learneds:

* Some are blank on dev site but some are not  
* The ones that are blank on the dev site are blank on the original site as well.  
* Not sure what main page these are housed under on the original site, but they can be searched for.

Middle-Quick-Links:

* Blank on the dev site: [https://dev.teachinghistory.org/middle-quick-links/quick-links-for-middle-school-teachers-24284/](https://dev.teachinghistory.org/middle-quick-links/quick-links-for-middle-school-teachers-24284/)  
* Same as the other quick links… When accessing from the link on the main page or the footer, the page appears just fine on the original site: [https://teachinghistory.org/quick-links-middle](https://teachinghistory.org/quick-links-middle) .The page that appears when searching for it on the original site is blank: [https://teachinghistory.org/node/24284](https://teachinghistory.org/node/24284)  
* Could this guide be a search filter instead of a separate page?


National-Resource-Centers: 

* Accessible by searching and from History Content under the title [National Resources](https://teachinghistory.org/history-content/national-resources).   
* 78 resources available to the public on the website.  
* 78 resources visible on the dev, the margins did not transfer over.

Pages: 

* This section has 99 resources, including landing pages (not sure what this called) for various content types (Teaching materials..) and some of the about pages. Some are blank and some are not and some are visible on one or both of the websites. Will probably need to go through and see what should be deleted and what should not be deleted.    
* Some of this content is Blank on both the Dev (only has a title) and the original site, but others are accessible on the original in different ways depending on the page.. The container which housed some of this type of content seems to have been removed. ![][image13]  
* Example: [https://teachinghistory.org/node/25738](https://teachinghistory.org/node/25738) , [https://teachinghistory.org/node/25725](https://teachinghistory.org/node/25725)  
* Another Example: Dev: Only Some of the content transferred over   
  * Dev:[https://dev.teachinghistory.org/page/interactive-historical-thinking-poster-secondary-25630/](https://dev.teachinghistory.org/page/interactive-historical-thinking-poster-secondary-25630/)   
  * Two versions of the page on the original, one with content and one without, Without content: [https://teachinghistory.org/node/25630](https://teachinghistory.org/node/25630) With Content: [https://teachinghistory.org/historical-thinking-poster-2](https://teachinghistory.org/historical-thinking-poster-2) under print materials accessible under outreach-print materials

Press-Releases: 

* In the about section and accessible in the footer  
* visible on the original, Blank on the dev  
* Some of the linked resources in the press releases are no longer available on the original website for example [https://teachinghistory.org/node/25392](https://teachinghistory.org/node/25392) the state standards are on the dev site but have been removed from the original website. 

Primary-Source-Guides \- 

* Called [Using Primary Source](https://teachinghistory.org/best-practices/using-primary-sources) and accessible from best practices on the original site  
* 38 resources on the dev margins did not transfer over, 38 resources on the original  
* The original includes some broken links to externally hosted websites and most of the embedded videos on the pages seems to no longer work \- [https://teachinghistory.org/best-practices/using-primary-sources/24079](https://teachinghistory.org/best-practices/using-primary-sources/24079) (Blank dev: [https://dev.teachinghistory.org/best-practices/using-primary-sources/24079/](https://dev.teachinghistory.org/best-practices/using-primary-sources/24079/)) 


Quizlies: 

* Accessible through the name [History Quiz](https://teachinghistory.org/history-content/quiz) on History Content   
* 124 results. Since most of the resources were created for the website and are embedded on their through pdfs we should not have to worry too much about checking links. Transferring this content over should be relatively simple once the content from the margins is transferred..   
* Content is blank on the dev. 124 resources. 

Research-Briefs: 

* Could not find these materials \- Ex. [https://teachinghistory.org/search/node?keys=Discussing%20Controversial%20Public%20Issues%20in%20the%20Classroom](https://teachinghistory.org/search/node?keys=Discussing%20Controversial%20Public%20Issues%20in%20the%20Classroom)   
* Content is on the Dev. 

Research-Tools: 

* accessible from Digital Classrooms \- called [Tech for Teachers](https://teachinghistory.org/digital-classroom/tech-for-teachers)  
* 72 resources seems like a good number of these hardware/software recommendations still exists although there are some dead links embedded within the page. These pages should be checked ([https://teachinghistory.org/digital-classroom/tech-for-teachers/20785](https://teachinghistory.org/digital-classroom/tech-for-teachers/20785)).    
  * One thing we would need to consider is if they are still useful recommendations or written in a way that is useful to how they exist at this moment.   
* Content is blank on the dev, 72 blank resources. 

Roundtable-Responses: 

* Not accessible on the website but the record still comes up when searching the website.    
* Content available on the dev.

Roundtables: 

* Not accessible on the website but the record still comes up when searching the website.  
* Content is blank on the dev.

Tah-Directors-Conference-Days: 

* Not accessible on the website but still comes up when searching the website.   
* Content is blank on the dev.

Tah-Directors-Conferences: 

* Not accessible on the website but still comes up when searching the website.   
* Content is blank on the dev. 

Tah-Grants: 

* Not accessible on the original website but still comes up when searching the website.   
* Content is blank on the dev. 

Teaching-Guides: 

* Accessible from teaching materials.   
* [Teaching Guides](https://teachinghistory.org/teaching-materials/teaching-guides) \- 43 resources visible on the original website, only 39 resources on the dev under this header the first four do not seem to have transferred over.   
* Will need to check this content for dead links. 

Teaching-Guides-Prototype-Children \- 

* Can be found while searching, and leads to a page with content on the original, but blank on the Dev site.   
* I am not sure if it is accessible any other way because it looks like the original container that held it on the webpage was deleted. These also do not seem like stand alone or complete pages, like they were linked to something else.   
  * [https://teachinghistory.org/search/node?keys=Using+Historical+Footage+%28High+School%29](https://teachinghistory.org/search/node?keys=Using+Historical+Footage+%28High+School%29) 

Teaching-Guides-Prototype-Gen-Ches: 

* I found these resources through searching and by looking on the referenced webpage [https://teachinghistory.org/visiting-history](https://teachinghistory.org/visiting-history) on the original website.   
* They are found somewhere in teaching materials. Clicking on the page shows it is somewhere under teacher materials but I could not find it on that page. [![][image14]](https://teachinghistory.org/teaching-materials/visiting-history/plan)  
* Blank on the dev site

Teaching-Guides-Prototype-Gens \- 

* Can be found through searching but I am not sure how to access it in any other way. [https://teachinghistory.org/search/node?keys=Visiting%20History%3A%20A%20Professional%20Development%20Guide](https://teachinghistory.org/search/node?keys=Visiting%20History%3A%20A%20Professional%20Development%20Guide)   
* Blank on the Dev site.


Teaching-Guides-Prototypes 

* [https://teachinghistory.org/teaching-materials/teaching-guides/24299](https://teachinghistory.org/teaching-materials/teaching-guides/24299) maybe gone but also may still be available through another webpage.  
* Blank on the Dev site

Teaching-Standards: 

* No longer accessible to the public on the original site but still comes up when you search for content. Is accessible on the Dev site. 

Teaching-With-Textbooks: 

* Visible on the dev and original website, margins did not copy over  
* Accessible through best practices \- [Teaching with Textbooks](https://teachinghistory.org/best-practices/teaching-with-textbooks)  
* 8 resources \- a few dead links embedded within the resource, but the content seems to have aged well.   
  * https://differentiationcentral.com/what-is-differentiated-instruction/

Webforms: 

* Not visible on the dev or the original website.  
* [https://teachinghistory.org/search/node?keys=TeachingHistory.org+Survey](https://teachinghistory.org/search/node?keys=TeachingHistory.org+Survey) probably available at some point but no longer available except through search which leads to an empty page. 

Websites:

* Many visible on the original website but not on the dev site.   
  * [https://teachinghistory.org/history-content/website-reviews/25144](https://teachinghistory.org/history-content/website-reviews/25144)  
  * [https://dev.teachinghistory.org/history-content/website-reviews/25144/](https://dev.teachinghistory.org/history-content/website-reviews/25144/)   
*  Called [Website Reviews](https://teachinghistory.org/history-content/website-reviews) and accessible through History Content.   
* This section seems to have  the most content \- 1068 but it seems like some of the websites no longer exist. Some effort will have to be made to go through all of the sites and remove or update the links.  
  * [https://teachinghistory.org/history-content/website-reviews/25826](https://teachinghistory.org/history-content/website-reviews/25826)   
  * [https://teachinghistory.org/history-content/website-reviews/22658](https://teachinghistory.org/history-content/website-reviews/22658) 

Workshops-and-Lectures: 

* maybe accessible at one point but no longer accessible on the original website and dev site.  
* Ex: [https://teachinghistory.org/search/node?keys=The+Iconography+of+Slavery](https://teachinghistory.org/search/node?keys=The+Iconography+of+Slavery)   
* 