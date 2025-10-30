# sitemapper.py
"""
Version 0.40

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
import re

class SitemapGenerator:
    def __init__(self, base_url, delay=1, ignore_woocommerce_urls=False):
        if not base_url.startswith(('http://', 'https://')):
            base_url = 'https://' + base_url
        self.base_url = self.normalize_url(base_url)
        self.delay = delay
        self.visited_urls = set()
        self.all_links = set()
        self.page_data = {}
        parsed_base = urlparse(base_url)
        self.domain = parsed_base.netloc
        self.scheme = parsed_base.scheme
        self.ignore_woocommerce_urls = ignore_woocommerce_urls
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        })

        # Extract base domain without www for comparison
        self.base_domain = self.get_base_domain(self.domain)

    def get_base_domain(self, domain):
        """Get the base domain without www prefix"""
        if domain.startswith('www.'):
            return domain[4:]
        return domain

    def normalize_url(self, url):
        """Normalize URL to avoid duplicates with/without trailing slashes"""
        parsed = urlparse(url)
        path = parsed.path.rstrip('/')
        normalized = f"{parsed.scheme}://{parsed.netloc}{path}"
        if parsed.query:
            normalized += f"?{parsed.query}"
        return normalized

    def is_same_domain(self, url):
        """Check if URL belongs to the same base domain (handles www vs non-www)"""
        parsed = urlparse(url)
        url_domain = parsed.netloc
        url_base_domain = self.get_base_domain(url_domain)
        
        # Compare base domains (treat www and non-www as same)
        return url_base_domain == self.base_domain

    def is_valid_url(self, url):
        """Check if URL belongs to the same domain and is valid"""
        parsed = urlparse(url)
        
        # Check if it's the same base domain
        if not self.is_same_domain(url):
            return False
            
        # Check if we should ignore WooCommerce action URLs
        if self.ignore_woocommerce_urls and self.woocommerce_ignore_cart_urls(url):
            return False
            
        # Ignore Cloudflare email protection and related non-content URLs
        if any(pattern in url.lower() for pattern in [
            'cdn-cgi/l/email-protection',
            '/cdn-cgi/',
            'wp-json/',
            'xmlrpc.php',
            'feed/',
            '.xml',
            '.rss'
        ]):
            return False
            
        # File extensions to ignore
        if any(parsed.path.lower().endswith(ext) for ext in [
            '.pdf', '.jpg', '.jpeg', '.png', '.gif', '.zip', 
            '.webp', '.mp4', '.mpeg', '.svg', '.css', '.js',
            '.ico', '.woff', '.woff2', '.ttf', '.eot'
        ]):
            return False
            
        # Regex pattern for file extensions anywhere in path
        if re.search(r'\.(pdf|jpg|jpeg|png|gif|zip|webp|mp4|mpeg|svg|css|js|ico|woff|woff2|ttf|eot)(\?|$|/)', url.lower()):
            return False
            
        return parsed.scheme in ['http', 'https']

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
            response = self.session.get(url, timeout=15)
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
                href = link['href'].strip()
                
                # Skip empty links, javascript links, and mailto links
                if not href or href.startswith(('javascript:', 'mailto:', 'tel:', '#')):
                    continue
                
                full_url = urljoin(url, href)
                
                # Remove anchor links before validation
                full_url = self.ignore_anchored_links(full_url)
                # Normalize URL to avoid duplicates
                full_url = self.normalize_url(full_url)
                
                # DEBUG: Show what we're checking
                parsed_full = urlparse(full_url)
                is_same_domain = self.is_same_domain(full_url)
                is_valid = self.is_valid_url(full_url)
                
                if is_valid and full_url not in links:
                    links.append(full_url)
                    print(f"    ✓ Found internal link: {full_url}")
                elif is_same_domain and not is_valid:
                    print(f"    ✗ Rejected same-domain URL: {full_url} (failed validation)")
                elif not is_same_domain:
                    print(f"    ✗ Rejected external URL: {full_url}")

            return links

        except requests.RequestException as e:
            print(f"Network error crawling {url}: {e}")
            return []
        except Exception as e:
            print(f"Error extracting links from {url}: {e}")
            return []

    def crawl_website(self, max_pages=100):
        """Crawl the website starting from base URL"""
        print("Starting crawl...")
        print(f"Target base domain: {self.base_domain}")
        print(f"Will crawl both www and non-www versions")
        
        urls_to_visit = {self.base_url}
        self.visited_urls.clear()
        self.all_links.clear()

        while urls_to_visit and len(self.visited_urls) < max_pages:
            current_url = urls_to_visit.pop()

            if current_url in self.visited_urls:
                continue

            print(f"\nCrawling [{len(self.visited_urls) + 1}/{max_pages}]: {current_url}")
            self.visited_urls.add(current_url)

            # Extract links, SEO title and H1 from the current page
            new_links = self.extract_links_and_titles(current_url)

            # Add new links to the queue
            for link in new_links:
                # Ensure no anchored links make it to the queue
                clean_link = self.ignore_anchored_links(link)
                # Normalize URL to avoid duplicates
                clean_link = self.normalize_url(clean_link)
                
                # DOUBLE CHECK before adding to queue
                if (clean_link not in self.visited_urls and 
                    clean_link not in urls_to_visit and 
                    self.is_valid_url(clean_link) and
                    self.is_same_domain(clean_link)):
                    urls_to_visit.add(clean_link)
                    self.all_links.add(clean_link)
                    print(f"    → Added to queue: {clean_link}")
                else:
                    print(f"    → Skipped (already visited/queued/invalid): {clean_link}")

            print(f"  Found {len(new_links)} links on this page")
            print(f"  Queue size: {len(urls_to_visit)}, Total discovered: {len(self.all_links) + 1}")

            # Graceful delay between requests
            if self.delay > 0:
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
        print(f"\nSitemap generated: {output_file}")
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
        
        print(f"\nCSV sitemap generated: {output_file}")
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
    
    if not website_url.startswith(('http://', 'https://')):
        website_url = 'https://' + website_url
        print(f"Added https:// -> {website_url}")
    
    max_pages = int(input("Enter maximum pages to crawl (default 1000): ") or "1000")
    
    # WooCommerce URL filtering choice
    print("\nWooCommerce URL Filtering:")
    print("Ignore WooCommerce URLs like cart, checkout, wishlist, etc.?")
    ignore_woocommerce = input("Ignore WooCommerce URLs? (y/N): ").strip().lower() == 'y'
    
    if ignore_woocommerce:
        print("✓ Will ignore WooCommerce URLs (cart, checkout, wishlist, etc.)")
    else:
        print("✓ Will include all URLs including WooCommerce pages")
    
    # Output format selection
    print("\nSelect output format:")
    print("1. CSV (Spreadsheet format) - RECOMMENDED")
    print("2. XML (Standard sitemap)")
    format_choice = input("Enter choice (1 or 2, default 1): ").strip() or "1"
    
    if format_choice == "1":
        output_file = input("Enter output filename (default sitemap.csv): ") or "sitemap.csv"
        output_file = add_file_extension(output_file, 'csv')
    else:
        output_file = input("Enter output filename (default sitemap.xml): ") or "sitemap.xml"
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
