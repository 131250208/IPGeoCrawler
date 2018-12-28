import scrapy
import pkgutil
from urllib import parse
from bs4 import BeautifulSoup
import re
import requests
import random
import time
import json
import logging
import sys


class OrganizationSpider(scrapy.Spider):
    name = "organizations"
    ORG_KEYWORDS = ["college", "company", "university", "school", "corporation",
                    "institute", "organization", "association"]

    HEADERS = {
        "Content-Type": "*/*",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "en-US,en;q=0.5",
        "Connection": "keep-alive",
        "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:39.0) Gecko/20100101 Firefox/39.0",
        "Referer": "https://github.com",
    }

    def try_best_2_get(self, url, params=None, max_times=999, invoked_by=None, proxies=None, get_proxies_fun=None, **kwargs):
        '''
        :param url:
        :param params:
        :param max_times: max times for trying
        :param invoked_by: invoked by which function, used to debug
        :param get_proxies_fun: invoke the get_proxies_fun every request if it's been set
        :param proxies: it does not work if the get_proxies_fun has been set
        :param kwargs:
        :return:
        '''
        error_count = 0
        if invoked_by is None:
            invoked_by = "not set"
        while True:
            try:
                if get_proxies_fun:
                    proxies = get_proxies_fun()
                res = requests.get(url, params=params, proxies=proxies, **kwargs)
                break
            except Exception as e:
                logging.warning("%s(invoked by: %s) go wrong..., attempt: %d" % (
                sys._getframe().f_code.co_name, invoked_by, error_count))
                logging.warning(e)
                random.seed(time.time())
                time.sleep(2 + 3 * random.random())
                error_count += 1
                if error_count > max_times:
                    logging.warning("max error_count exceeded: %d" % (max_times))
                    return None
        return res

    def start_requests(self):
        def quote(queryStr):
            try:
                queryStr = parse.quote(queryStr)
            except:
                queryStr = parse.quote(queryStr.encode('utf-8', 'ignore'))
            return queryStr

        while True:
            data = pkgutil.get_data("ipgeo_rel_data_crawlers", "Sources/query_seed_dict.json")
            seed_dict = json.loads(data)
            query_list = [q for q in seed_dict.keys() if seed_dict[q] == 0]
            for query in query_list:
                query = quote(query)
                url = 'https://www.google.com/search?biw=1920&safe=active&hl=en&q=%s&oq=%s' % (query, query)
                yield scrapy.Request(url=url, callback=self.parse, meta={"query_str": query})

    def parse(self, response):
        query_str = response.meta["query_str"]
        rel_org_name_set = set()
        text = response.body
        soup = BeautifulSoup(text, "lxml")

        # it there an entity in google KG?
        div_kg_hearer = soup.select_one("div.kp-header")

        if div_kg_hearer is None:  # if there is no knowledge graph at the right, drop it
            return None

        enti_name = div_kg_hearer.select_one("div[role=heading] span")
        enti_name = enti_name.text if enti_name is not None else None
        if enti_name is None or "..." in enti_name:
            se = re.search('\["t-dhmk9MkDbvI",.*\[\["data",null,null,null,null,\[null,"\[\\\\"(.*)\\\\",', text)
            if se is not None:
                enti_name = se.group(1)
            else:
                return None

        # identify the type
        span_list = div_kg_hearer.select("span")
        enti_type = span_list[-1].text if len(span_list) > 1 else "unknown"

        # description from wikipedia
        des = soup.find("h3", text="Description")
        des_info = ""
        if des is not None:
            des_span = des.parent.select_one("span")
            des_info = des_span.text if des_span is not None else ""

        # identify whether it is a organization
        pattern_org = "(%s)" % "|".join(self.ORG_KEYWORDS)
        se = re.search(pattern_org, enti_type, flags=re.I)
        is_org = True
        if se is None:
            is_org = False

        # extract attributes
        attr_tags = soup.select("div.Z1hOCe")
        attr_dict = {}
        for attr in attr_tags:
            attr_str = attr.get_text()
            se = re.search("(.*?)[:：](.*)", attr_str)
            if se is None:
                continue
            key_attr = se.group(1)
            val_attr = se.group(2)
            attr_dict[key_attr] = val_attr

        # relevant org name on current page
        a_reltype_list = soup.select("div.MRfBrb > a")
        for a in a_reltype_list:
            rel_org_name_set.add(a["title"].strip())

        # collect next urls e.g. : more x+
        div_list = soup.select("div.yp1CPe")
        next = []
        host = "https://www.google.com"
        for div in div_list:
            a_list = div.select("a.EbH0bb")
            for a in a_list:
                if "http" not in a["href"]:
                    next.append("%s%s" % (host, a["href"]))

        # crawl parent org
        a_parent_org = soup.find("a", text="Parent organization")
        if a_parent_org is not None:
            parent_str = a_parent_org.parent.parent.text.strip()
            parent_org = parent_str.split(":")[1]
            rel_org_name_set.add(parent_org.strip())

        # crawl subsidiaries
        a_subsidiaries = soup.find("a", text="Subsidiaries")
        if a_subsidiaries is not None:
            href = a_subsidiaries["href"]
            if "http" not in href:
                subsidiaries_str = a_subsidiaries.parent.parent.text.strip()
                subs = subsidiaries_str.split(":")[1].split(",")
                for sub in subs:
                    sub = sub.strip()
                    if sub == "MORE":
                        continue
                    rel_org_name_set.add(sub)
                next.append("%s%s" % (host, href))

        # scrawl urls in list 'next'
        for url in next:
            res = self.try_best_2_get(url, headers=self.HEADERS, timeout=20)
            soup = BeautifulSoup(res.text, "lxml")

            # crawl items at the top
            a_list = soup.select("a.klitem")
            for a in a_list:
                rel_org_name = a["title"]
                rel_org_name_set.add(rel_org_name.strip())

            # crawl headings under the map if any
            heading_list = soup.select("div.VkpGBb")
            for heading in heading_list:
                heading_str = heading.select_one("div[role='heading']")
                rel_org_name_set.add(heading_str.get_text())

            random.seed(time.time())
            time.sleep(1 + 3 * random.random())

        rel_org_name_list = [org_name for org_name in rel_org_name_set if len(org_name) > 1]
        yield {"query_str": query_str, "name": enti_name, "type": enti_type, "is_org": is_org,
                "des": des_info, "attributes": attr_dict, "rel_org": rel_org_name_list}
