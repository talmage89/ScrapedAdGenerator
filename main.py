import argparse
import os.path
import re
import shutil

from dotenv import load_dotenv

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI


logDirectory = "logs"

# create log directory if needed and remove contents
try:
    os.mkdir(logDirectory)
except Exception:
    pass
for filename in os.listdir(logDirectory):
    file_path = os.path.join(logDirectory, filename)
    if os.path.isfile(file_path) or os.path.islink(file_path):
        os.remove(file_path)
    elif os.path.isdir(file_path):
        shutil.rmtree(file_path)


def log(filename, content):
    with open(
        os.path.join(logDirectory, filename), "w", encoding="utf-8", errors="replace"
    ) as file:
        file.write(content)


def get_file_as_string(filepath):
    data_str = ""
    with open(filepath, "r") as file:
        data_str = file.read()
    return data_str


def scraper_error(soup, rejection_keywords):
    page_text = soup.get_text(" ").lower()

    for keyword in rejection_keywords:
        if keyword in page_text:
            return True

    return False


def access_denied(soup):
    return scraper_error(
        soup,
        [
            "access denied",
            "forbidden",
            "unauthorized",
            "403 forbidden",
            "401 unauthorized",
        ],
    )


def need_to_enable_javascript(soup):
    return scraper_error(soup, ["enable javascript"])


def extract_data(soup, force):
    extracted = ""
    if not force:
        if access_denied(soup):
            raise Exception(
                "It looks like this site has denied access to our scraper. Use the --force flag to override this error."
            )
        elif need_to_enable_javascript(soup):
            raise Exception(
                "It looks like this site is unreadable by our scraper. Improve your SEO and try again."
            )
    # title tag
    title = soup.title.string if soup.title else None
    if title:
        extracted += f"Title Tag: {title}\n\n"
    # other head tags
    head_tags = soup.find_all("meta", attrs={"name": re.compile("description")})
    head_tags_str = ""
    for tag in head_tags[0:10]:
        tag_str = "Meta Tag -- "
        for attr_name in tag.attrs.keys():
            tag_str += f"{attr_name}: {tag[attr_name]};"
        head_tags_str += f"{tag_str}\n"
    if len(head_tags) > 0:
        extracted += f"{head_tags_str}\n"
    # body
    body = soup.body
    if body:
        body_str = body.get_text(" ", strip=True)
        extracted += f"Body Tag:\n{body_str[0:4000]}\n\n"
    return extracted


def scrape_data(url):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_extra_http_headers(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36"
            }
        )
        page.goto(url, wait_until="networkidle")
        page.wait_for_selector("body")
        content = page.content()
        browser.close()
        return content


def generate_advertisement(data, tone):
    system_template = get_file_as_string('./system_prompt.txt')
    prompt_template = ChatPromptTemplate.from_messages(
        [("system", system_template), ("user", "TONE: {tone};\nDATA: {data}")]
    )
    model = ChatOpenAI(model="gpt-4")
    parser = StrOutputParser()
    chain = prompt_template | model | parser
    return chain.invoke({"tone": tone, "data": data})


def main():
    # set up command line arguments
    parser = argparse.ArgumentParser(
        description="Scrape website data and create a social media post."
    )
    parser.add_argument(
        "site_url", type=str, help="The site you would like to scrape your data from."
    )
    parser.add_argument("--tone", type=str, help="Tone of the generated advertisement.")
    parser.add_argument(
        "--force",
        type=bool,
        help="Force advertisement generation even if our scraper detects an error.",
    )
    args = parser.parse_args()
    url = args.site_url if args.site_url else "https://startstudio.com/"
    tone = args.tone if args.tone else "Professional"
    force = args.force

    # pull site html and attempt to extract useful data
    print(f"Site to scrape: {url}")
    print("Starting scrape.\n")
    site_content = scrape_data(url)
    soup = BeautifulSoup(site_content, "html.parser")
    log("scraped.html", soup.prettify())
    try:
        extracted_data = extract_data(soup, force)
    except Exception as e:
        print(f"{e}\n")
        return 1
    print("Extracted data:")
    print(extracted_data)

    # perform generation
    print(f"Requested tone: {tone}")
    print("Starting advertisement generation.")
    load_dotenv()
    generated = generate_advertisement(extracted_data, tone)
    log("generated.txt", generated)
    print("Finished generation.\n\n")
    print(generated)

    return 0


if __name__ == "__main__":
    main()
