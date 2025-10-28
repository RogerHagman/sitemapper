# sitemapper.py
"""
Version 0.36

Sitemapcrawler generates a XML or CSV sitemap of a website, 
including SEO titles and H1 tags.

Features:
- Crawls a website starting from a base URL
- Extracts all internal links, SEO titles, and H1 tags
- Generates an XML sitemap or CSV file with the extracted data

Author: Roger Hagman
"""

# Imports
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import xml.etree.ElementTree as ET
from datetime import datetime
import time
import csv
import os

class SitemapGenerator:
    def __init__(self, base_url, delay=1, ignore_woocommerce_urls=False):
        # Automatically add https:// if it was not provided by the user
        if not base_url.startswith(('http://', 'https://')):
            base_url = 'https://' + base_url
        self.base_url = self.normalize_url(base_url)  # Normalize base URL
        self.delay = delay
        self.visited_urls = set()
        self.all_links = set()
        self.page_data = {}
        self.domain = urlparse(base_url).netloc
        self.ignore_woocommerce_urls = ignore_woocommerce_urls

    def normalize_url(self, url):
        """Normalize URL to avoid duplicates with/without trailing slashes"""
        parsed = urlparse(url)
        # Remove trailing slash from path and rebuild URL
        path = parsed.path.rstrip('/')
        normalized = f"{parsed.scheme}://{parsed.netloc}{path}"
        if parsed.query:
            normalized += f"?{parsed.query}"
        return normalized

    def is_valid_url(self, url):
        """Check if URL belongs to the same domain and is valid"""
        parsed = urlparse(url)
        
        # Check if we should ignore WooCommerce action URLs
        if self.ignore_woocommerce_urls and self.woocommerce_ignore_cart_urls(url):
            return False
            
        return (parsed.netloc == self.domain and
                parsed.scheme in ['http', 'https'] and
                # Ignore common non-HTML file types
                not url.endswith(('.pdf', '.jpg', '.png', '.zip', 'webp', 'mp4', 'mpeg', 'svg')))

    def ignore_anchored_links(self, url):
        """Remove anchor links from URLs to avoid duplicates in sitemap"""
        return url.split('#')[0]

    def extract_seo_title_and_h1(self, url, soup):
        """Extract SEO title and H1 metadata from a page"""
        try:
            # Extract SEO title from <title> tag
            title_tag = soup.find('title')
            seo_title = title_tag.string.strip() if title_tag and title_tag.string else "No SEO title found"
            
            # Extract H1 content
            h1_tag = soup.find('h1')
            h1_content = h1_tag.get_text().strip() if h1_tag else "No H1 found"
            
            return seo_title, h1_content
            
        except Exception as e:
            print(f"Error extracting titles from {url}: {e}")
            return "Error extracting SEO title", "Error extracting H1"

    def extract_links_and_titles(self, url):
        """Extract all links, SEO title and H1 from a page"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract and store SEO title and H1
            seo_title, h1_content = self.extract_seo_title_and_h1(url, soup)
            self.page_data[url] = {
                'seo_title': seo_title,
                'h1_content': h1_content,
                'lastmod': datetime.now().strftime('%Y-%m-%d')
            }
            
            print(f"  SEO Title: {seo_title}")
            print(f"  H1: {h1_content}")
            
            links = []

            for link in soup.find_all('a', href=True):
                full_url = urljoin(url, link['href'])
                
                # Remove anchor links before validation
                full_url = self.ignore_anchored_links(full_url)
                # Normalize URL to avoid duplicates
                full_url = self.normalize_url(full_url)
                
                if self.is_valid_url(full_url) and full_url not in links:
                    links.append(full_url)

            return links

        except Exception as e:
            print(f"Error extracting links from {url}: {e}")
            return []

    def crawl_website(self, max_pages=100):
        """Crawl the website starting from base URL"""
        urls_to_visit = {self.base_url}

        while urls_to_visit and len(self.visited_urls) < max_pages:
            current_url = urls_to_visit.pop()

            if current_url in self.visited_urls:
                continue

            print(f"Crawling: {current_url}")
            self.visited_urls.add(current_url)

            # Extract links, SEO title and H1 from the current page
            new_links = self.extract_links_and_titles(current_url)

            # Add new links to the queue
            for link in new_links:
                # Ensure no anchored links make it to the queue
                clean_link = self.ignore_anchored_links(link)
                # Normalize URL to avoid duplicates
                clean_link = self.normalize_url(clean_link)
                if clean_link not in self.visited_urls:
                    urls_to_visit.add(clean_link)
                    self.all_links.add(clean_link)

            # Graceful delay between requests
            time.sleep(self.delay)

    def generate_sitemap(self, output_file='sitemap.xml'):
        """Generate XML sitemap with titles"""
        urlset = ET.Element('urlset')
        urlset.set('xmlns', 'http://www.sitemaps.org/schemas/sitemap/0.9')

        # Add base URL first
        self.add_url_to_sitemap(urlset, self.base_url)

        # Add all discovered URLs (ensuring no anchored links)
        for url in self.all_links:
            clean_url = self.ignore_anchored_links(url)
            clean_url = self.normalize_url(clean_url)  # Normalize again for safety
            self.add_url_to_sitemap(urlset, clean_url)

        # Create XML tree and write to file
        tree = ET.ElementTree(urlset)
        tree.write(output_file, encoding='utf-8', xml_declaration=True)
        print(f"Sitemap generated: {output_file}")
        print(f"Total URLs found: {len(self.all_links) + 1}")

    def add_url_to_sitemap(self, urlset, url):
        """Add a URL to the sitemap with SEO title and current date"""
        url_element = ET.SubElement(urlset, 'url')

        loc = ET.SubElement(url_element, 'loc')
        loc.text = url

        # Add SEO title if available
        if url in self.page_data:
            seo_title_element = ET.SubElement(url_element, 'seo_title')
            seo_title_element.text = self.page_data[url]['seo_title']
            
            # Add H1 content if available
            h1_element = ET.SubElement(url_element, 'h1')
            h1_element.text = self.page_data[url]['h1_content']

        lastmod = ET.SubElement(url_element, 'lastmod')
        # Use stored lastmod or current date
        if url in self.page_data:
            lastmod.text = self.page_data[url]['lastmod']
        else:
            lastmod.text = datetime.now().strftime('%Y-%m-%d')

    def generate_csv(self, output_file='sitemap.csv'):
        """Generate CSV sitemap with SEO title and H1"""
        # Combine all URLs (base URL + discovered links)
        all_urls = [self.base_url] + list(self.all_links)
        
        # Use a set to remove duplicates after normalization
        unique_urls = set()
        for url in all_urls:
            normalized_url = self.normalize_url(url)
            unique_urls.add(normalized_url)
        
        # Convert back to sorted list
        unique_urls = sorted(unique_urls)
        
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            
            # SEO Title and H1
            writer.writerow(['SEO Title', 'H1', 'Permalinks', 'Date Crawled'])

            # Data rows to include both SEO Title and H1
            for url in unique_urls:
                clean_url = self.ignore_anchored_links(url)
                seo_title = self.page_data.get(url, {}).get('seo_title', 'Not crawled')
                h1_content = self.page_data.get(url, {}).get('h1_content', 'Not crawled')
                lastcrawled = self.page_data.get(url, {}).get('lastmod', datetime.now().strftime('%Y-%m-%d'))
                
                writer.writerow([
                    seo_title,
                    h1_content,
                    clean_url,
                    lastcrawled
                ])
        
        print(f"CSV sitemap generated: {output_file}")
        print(f"Total URLs found: {len(unique_urls)}")

    def woocommerce_ignore_cart_urls(self, url):
        """Ignore WooCommerce cart, wishlist and checkout in URLs"""
        woocommerce_terms = ['cart', 'wishlist', 'checkout', 'add-to-cart', 'my-account']
        
        # Check both in the path and query parameters
        parsed_url = urlparse(url)
        url_lower = url.lower()
        
        # Check path for WooCommerce terms
        for term in woocommerce_terms:
            if term in parsed_url.path.lower():
                return True
        
        # Check query parameters for WooCommerce terms
        if '?' in url:
            for term in woocommerce_terms:
                if term in url_lower:
                    return True
        
        return False

def add_file_extension(filename, default_extension):
    """Add file extension if not present"""
    name, ext = os.path.splitext(filename)
    if not ext:
        return f"{filename}.{default_extension}"
    return filename

def main():
    # Configuration
    website_url = input("Enter website URL (e.g., https://example.com): ").strip()
    
    # Automatically add https:// if full url was not provided
    if not website_url.startswith(('http://', 'https://')):
        website_url = 'https://' + website_url
        print(f"Added https:// -> {website_url}")
    
    max_pages = \
      int(input("Enter maximum pages to crawl (default 1000): ") or "1000")
    
    # WooCommerce URL filtering choice
    print("\nWooCommerce URL Filtering:")
    print("Ignore WooCommerce URLs like cart, checkout, wishlist, etc.?")
    ignore_woocommerce = \
      input("Ignore WooCommerce URLs? (y/N): ").strip().lower() == 'y'
    
    if ignore_woocommerce:
        print("✓ Will ignore WooCommerce URLs (cart, checkout, wishlist, etc.)")
    else:
        print("✓ Will include all URLs including WooCommerce pages")
    
    # Output format selection (CSV is now first choice)
    print("\nSelect output format:")
    print("1. CSV (Spreadsheet format) - RECOMMENDED")
    print("2. XML (Standard sitemap)")
    format_choice = input("Enter choice (1 or 2, default 1): ").strip() or "1"
    
    if format_choice == "1":
        output_file = \
          input("Enter output filename (default sitemap.csv): ") or "sitemap.csv"
        output_file = add_file_extension(output_file, 'csv')
    else:
        output_file = \
          input("Enter output filename (default sitemap.xml): ") or "sitemap.xml"
        output_file = add_file_extension(output_file, 'xml')

    # Generate sitemap
    generator = SitemapGenerator(website_url, ignore_woocommerce_urls=ignore_woocommerce)
    generator.crawl_website(max_pages=max_pages)
    
    # Generate appropriate format
    if format_choice == "1":
        generator.generate_csv(output_file)
    else:
        generator.generate_sitemap(output_file)

if __name__ == "__main__":
    main()
