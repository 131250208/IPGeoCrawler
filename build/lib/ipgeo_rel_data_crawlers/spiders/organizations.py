import scrapy
import json
from urllib import parse
from bs4 import BeautifulSoup

class OrganizationSpider(scrapy.Spider):
    name = "organizations"

    def quote(self, queryStr):
        try:
            queryStr = parse.quote(queryStr)
        except:
            queryStr = parse.quote(queryStr.encode('utf-8', 'ignore'))

        return queryStr

    def start_requests(self):
        org_names_dict = json.load(open("Sources/org_names_1.json", "r"))
        list_url = [{"query_org": org_name, "url": 'https://www.google.com/search?biw=1920&safe=active&hl=en&q=%s&oq=%s' % (org_name, org_name)} for org_name in org_names_dict.keys() if org_names_dict[org_name] == 0]
        for url in list_url:
            yield scrapy.Request(url=url["url"], callback=self.parse, meta={"query_org": url["query_org"]})

    def parse(self, response):
        query_org = response.meta["query_org"]
        soup = BeautifulSoup(response.text, "lxml")
        div_list = soup.select("div[data-md='133']")
        next = []
        host = "https://www.google.com"
        for div in div_list:
            a_list = div.select("a.EbH0bb")
            for a in a_list:
                next.append("%s%s" % (host, a["href"]))
        a = soup.find("a", text="People also search for")
        if a is not None:
            next.append("%s%s" % (host, a["href"]))

        for url in next:
            yield scrapy.Request(url=url, callback=self.get_rel_org_names, meta={"query_org": query_org})

    def get_rel_org_names(self, response):
        query_org = response.meta["query_org"]
        soup = BeautifulSoup(response.text, "lxml")
        a_list = soup.select("a.klitem")
        rel_org_name_set = set()
        for a in a_list:
            rel_org_name = a["title"]
            rel_org_name_set.add(rel_org_name)

        yield {
            "query_org": query_org,
            "rel_orgs": list(rel_org_name_set),
        }
