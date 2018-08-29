from lxml import html
import requests
import json
import urlparse

URL_APPENDIX_OVERVIEW = 'episodenguide'
S_COL = 3
EP_COL = 4
DE_EP_NAME = 6


def scrape(url):
    overview_url = urlparse.urljoin(url, URL_APPENDIX_OVERVIEW)
    print "Fetching", overview_url
    page = requests.get(overview_url)
    tree = html.fromstring(page.content)
    trs = tree.xpath('//*[@class="episodenliste"]//tr')
    row_length = 4
    current_col = 0
    row_data = []
    ep_data = {}
    ep_data_by_title = {}

    print "found %d rows" % len(trs)

    for tr in trs:
        tds = tr.findall("td")
        current_col = 0
        ep_data = {'title': '', 's_x_ep': ''}
        s_nr = ''
        ep_nr = ''
        s_x_ep = ''
        title = ''
        for td in tds:
            if current_col == S_COL:
                s_nr = td.text_content().replace(".", "").zfill(2)
            if current_col == EP_COL:
                ep_nr = td.text_content()
            if current_col == DE_EP_NAME:
                title_list = td.findall('span[@itemprop="name"]')
                if title_list:
                    title = title_list[0].text_content()
            current_col += 1

        print "S", s_nr, "E", ep_nr, "Title", title

        if s_nr and ep_nr and title:
            ep_data['s_x_ep'] = "%sx%s" % (s_nr, ep_nr)
            ep_data['title'] = title
            row_data.append(ep_data)

    print "row_data", row_data

    for row in row_data:
        title = row['title'].replace("??", "'")
        s_x_ep = row['s_x_ep']
        if title:
            ep_data[s_x_ep] = title
            ep_data_by_title[title] = s_x_ep

    for k, v in ep_data_by_title.items():
        print u"%s  -- %s" % (k, v)


scrape("https://www.fernsehserien.de/disneys-classic-cartoon/")
