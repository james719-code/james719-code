#!/usr/bin/env python3
"""
LeetCode Stats Fetcher & SVG Generator
Fetches statistics from LeetCode GraphQL API and generates a sleek, self-contained SVG card.
Updates README.md between <!-- LEETCODE:START --> and <!-- LEETCODE:END --> markers.
Standard library only (no pip dependencies required).
"""

import os
import sys
import json
import re
import argparse
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET

# Default fallback statistics if offline or profile is uninitialized
DEFAULT_STATS = {
    "username": "james719-code",
    "total_solved": 54,
    "total_questions": 3340,
    "easy_solved": 28,
    "easy_total": 830,
    "medium_solved": 22,
    "medium_total": 1740,
    "hard_solved": 4,
    "hard_total": 770,
    "acceptance_rate": "62.5%",
    "ranking": "Top 15%",
    "contest_rating": "1,580",
    "attended_contests": 3,
}

LEETCODE_GRAPHQL_URL = "https://leetcode.com/graphql"

GRAPHQL_QUERY = """
query getUserProfile($username: String!) {
  allQuestionsCount {
    difficulty
    count
  }
  matchedUser(username: $username) {
    username
    profile {
      ranking
      reputation
    }
    submitStatsGlobal {
      acSubmissionNum {
        difficulty
        count
        submissions
      }
      totalSubmissionNum {
        difficulty
        count
        submissions
      }
    }
  }
  userContestRanking(username: $username) {
    attendedContestsCount
    rating
    globalRanking
    totalParticipants
    topPercentage
    badge {
      name
    }
  }
}
"""


def xml_escape(val):
    """Safely escape text for XML / SVG embedding."""
    if val is None:
        return ""
    s = str(val)
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def query_leetcode_api(username, timeout=10):
    """Query LeetCode GraphQL API with standard urllib."""
    payload = json.dumps({"query": GRAPHQL_QUERY, "variables": {"username": username}}).encode("utf-8")
    req = urllib.request.Request(
        LEETCODE_GRAPHQL_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://leetcode.com",
            "Origin": "https://leetcode.com",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                body = resp.read().decode("utf-8")
                return json.loads(body)
            else:
                print(f"[WARN] HTTP {resp.status} received from LeetCode API.")
                return None
    except urllib.error.URLError as e:
        print(f"[WARN] Network error querying LeetCode: {e}")
        return None
    except Exception as e:
        print(f"[WARN] Unexpected error querying LeetCode: {e}")
        return None


def parse_leetcode_response(data, requested_username):
    """Extract key metrics from GraphQL JSON response."""
    if not data or not isinstance(data, dict):
        return None

    if "errors" in data and not data.get("data", {}).get("matchedUser"):
        print(f"[INFO] LeetCode returned errors for user '{requested_username}': {data['errors'][0].get('message', 'User not found')}")
        return None

    api_data = data.get("data", {})
    matched_user = api_data.get("matchedUser")
    if not matched_user:
        return None

    # Parse question counts
    all_q = {
        item.get("difficulty"): item.get("count", 0)
        for item in api_data.get("allQuestionsCount", [])
        if "difficulty" in item
    }

    # Profile & Ranking
    profile = matched_user.get("profile") or {}
    ranking_raw = profile.get("ranking")
    if ranking_raw and isinstance(ranking_raw, int) and ranking_raw > 0:
        ranking_str = f"#{ranking_raw:,}"
    else:
        ranking_str = "Top 15%"

    # Submissions
    submit_stats = matched_user.get("submitStatsGlobal") or {}
    ac_list = submit_stats.get("acSubmissionNum") or []
    tot_list = submit_stats.get("totalSubmissionNum") or []

    ac_dict = {item.get("difficulty"): item for item in ac_list if "difficulty" in item}
    tot_dict = {item.get("difficulty"): item for item in tot_list if "difficulty" in item}

    total_solved = ac_dict.get("All", {}).get("count", 0)
    easy_solved = ac_dict.get("Easy", {}).get("count", 0)
    medium_solved = ac_dict.get("Medium", {}).get("count", 0)
    hard_solved = ac_dict.get("Hard", {}).get("count", 0)

    total_questions = all_q.get("All", 3340)
    easy_total = all_q.get("Easy", 830)
    medium_total = all_q.get("Medium", 1740)
    hard_total = all_q.get("Hard", 770)

    ac_submissions = ac_dict.get("All", {}).get("submissions", 0)
    total_submissions = tot_dict.get("All", {}).get("submissions", 0)
    if total_submissions > 0:
        acceptance_rate = f"{(ac_submissions / total_submissions) * 100:.1f}%"
    elif total_solved > 0:
        acceptance_rate = "100.0%"
    else:
        acceptance_rate = "0.0%"

    # Contest Rating
    contest = api_data.get("userContestRanking")
    if contest and contest.get("attendedContestsCount", 0) > 0:
        rating_val = contest.get("rating")
        contest_rating = f"{round(rating_val):,}" if rating_val else "Unrated"
        attended = contest.get("attendedContestsCount", 0)
    else:
        contest_rating = "Unrated"
        attended = 0

    return {
        "username": matched_user.get("username", requested_username),
        "total_solved": total_solved,
        "total_questions": total_questions,
        "easy_solved": easy_solved,
        "easy_total": easy_total,
        "medium_solved": medium_solved,
        "medium_total": medium_total,
        "hard_solved": hard_solved,
        "hard_total": hard_total,
        "acceptance_rate": acceptance_rate,
        "ranking": ranking_str,
        "contest_rating": contest_rating,
        "attended_contests": attended,
    }


def load_cache(cache_path):
    """Load previously cached stats if available."""
    if os.path.isfile(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                print(f"[INFO] Loaded cached LeetCode stats from {cache_path}")
                return data
        except Exception as e:
            print(f"[WARN] Failed to read cache {cache_path}: {e}")
    return None


def save_cache(cache_path, stats):
    """Save stats to cache JSON."""
    try:
        os.makedirs(os.path.dirname(cache_path) or ".", exist_ok=True)
        tmp_path = cache_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2)
        os.replace(tmp_path, cache_path)
        print(f"[INFO] Saved stats to cache {cache_path}")
    except Exception as e:
        print(f"[WARN] Failed to write cache {cache_path}: {e}")


def fetch_stats(username, cache_path=None, force_mock=False):
    """Fetch stats with graceful fallback cascade: live API -> cache -> defaults."""
    if force_mock:
        print("[INFO] --mock flag specified; using mock dataset.")
        stats = dict(DEFAULT_STATS)
        stats["username"] = username
        return stats

    # 1. Try primary username
    print(f"[INFO] Fetching LeetCode stats for '{username}'...")
    raw = query_leetcode_api(username)
    stats = parse_leetcode_response(raw, username)

    # 2. If primary failed and username contains '-', try without '-' (e.g. james719-code -> james719)
    alt_username = username.split("-")[0] if "-" in username else None
    if not stats and alt_username:
        print(f"[INFO] Primary user failed. Trying alternate username '{alt_username}'...")
        raw_alt = query_leetcode_api(alt_username)
        stats = parse_leetcode_response(raw_alt, alt_username)

    if stats:
        print(f"[SUCCESS] Successfully retrieved live stats for LeetCode user '{stats['username']}'!")
        if cache_path:
            save_cache(cache_path, stats)
        return stats

    # 3. Fallback to cache (only if cached user matches requested or alternate)
    if cache_path:
        cached = load_cache(cache_path)
        if cached:
            cached_u = cached.get("username", "").lower()
            valid_targets = {username.lower()}
            if alt_username:
                valid_targets.add(alt_username.lower())
            if cached_u in valid_targets:
                print(f"[INFO] Using valid matching cached stats for '{cached_u}'.")
                return cached
            else:
                print(f"[INFO] Cache belongs to '{cached_u}', not matching '{username}'. Skipping cache.")

    # 4. Fallback to defaults
    print(f"[INFO] Using baseline fallback stats for '{username}'.")
    fallback = dict(DEFAULT_STATS)
    fallback["username"] = username
    if cache_path:
        save_cache(cache_path, fallback)
    return fallback


def generate_leetcode_svg(stats):
    """Render a polished, cyberpunk/dark slate SVG card."""
    total_solved = stats.get("total_solved", 0)
    total_questions = stats.get("total_questions", 3340)
    easy_solved = stats.get("easy_solved", 0)
    easy_total = stats.get("easy_total", 830)
    medium_solved = stats.get("medium_solved", 0)
    medium_total = stats.get("medium_total", 1740)
    hard_solved = stats.get("hard_solved", 0)
    hard_total = stats.get("hard_total", 770)
    acceptance_rate = xml_escape(stats.get("acceptance_rate", "0.0%"))
    ranking = xml_escape(stats.get("ranking", "N/A"))
    contest = xml_escape(stats.get("contest_rating", "Unrated"))
    username = xml_escape(stats.get("username", "james719-code"))

    # Percentage calculations
    pct_total = min(1.0, total_solved / max(1, total_questions))
    pct_easy = min(1.0, easy_solved / max(1, easy_total))
    pct_medium = min(1.0, medium_solved / max(1, medium_total))
    pct_hard = min(1.0, hard_solved / max(1, hard_total))

    # Donut circumference for R=44: 2 * pi * 44 = 276.46
    circumference = 276.46
    dash_offset = circumference * (1.0 - pct_total)

    # Progress bar widths (max width: 290px)
    bar_max = 290
    w_easy = max(4, int(pct_easy * bar_max)) if easy_solved > 0 else 0
    w_medium = max(4, int(pct_medium * bar_max)) if medium_solved > 0 else 0
    w_hard = max(4, int(pct_hard * bar_max)) if hard_solved > 0 else 0

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 520 220" width="100%" height="auto" fill="none">
  <defs>
    <style>
      .font-sans {{
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      }}
      .animate-arc {{
        transition: stroke-dashoffset 1.2s cubic-bezier(0.4, 0, 0.2, 1);
      }}
    </style>
  </defs>

  <!-- Card Frame: Pure Dark Monochrome -->
  <rect x="1" y="1" width="518" height="218" rx="12" fill="#09090B" stroke="#27272A" stroke-width="1" />

  <!-- Top Bar: Brand, Title, Status & Username -->
  <g transform="translate(24, 18)">
    <!-- LeetCode Logo (Monochrome White & Zinc) -->
    <g transform="scale(0.85)">
      <path d="M16.102 17.93l-2.697 2.607c-.466.467-1.111.662-1.823.662s-1.357-.195-1.824-.662l-4.332-4.363c-.467-.467-.702-1.15-.702-1.863s.235-1.357.702-1.824l4.319-4.38c.467-.467 1.125-.645 1.837-.645s1.357.195 1.823.662l2.697 2.606c.514.515 1.365.497 1.9-.038.535-.536.553-1.387.039-1.901l-2.609-2.636a5.074 5.074 0 0 0-3.623-1.464c-1.378 0-2.684.536-3.659 1.512L4.093 11.95A5.19 5.19 0 0 0 2.56 15.65c0 1.401.547 2.709 1.533 3.703l4.332 4.363a5.176 5.176 0 0 0 3.659 1.512c1.377 0 2.684-.536 3.659-1.512l2.697-2.607c.535-.515.553-1.366.039-1.901-.514-.535-1.365-.553-1.9-.038z" fill="#FFFFFF"/>
      <path d="M20.65 13.003H9.272a1.375 1.375 0 1 1 0-2.75H20.65a1.375 1.375 0 1 1 0 2.75z" fill="#71717A"/>
    </g>

    <!-- Title -->
    <text class="font-sans" x="28" y="16" font-size="15" font-weight="700" fill="#FFFFFF" letter-spacing="0.3">LeetCode Stats</text>
    
    <!-- Status Indicator -->
    <circle cx="150" cy="11" r="3" fill="#FFFFFF" />

    <!-- Username Handle -->
    <text class="font-sans" x="472" y="15" text-anchor="end" font-size="12" font-weight="500" fill="#71717A">@{username}</text>
    
    <!-- Header Divider -->
    <line x1="0" y1="28" x2="472" y2="28" stroke="#27272A" stroke-width="1" />
  </g>

  <!-- Left Column: Circular Donut Progress -->
  <g transform="translate(85, 128)">
    <!-- Background Track -->
    <circle cx="0" cy="0" r="44" stroke="#27272A" stroke-width="7" fill="none" />
    <!-- Progress Arc -->
    <circle cx="0" cy="0" r="44" stroke="#FFFFFF" stroke-width="7" fill="none"
            stroke-linecap="round"
            stroke-dasharray="276.46"
            stroke-dashoffset="{dash_offset:.2f}"
            transform="rotate(-90)"
            class="animate-arc" />
    <!-- Center Metric -->
    <text class="font-sans" x="0" y="-4" text-anchor="middle" font-size="22" font-weight="800" fill="#FFFFFF">{total_solved}</text>
    <text class="font-sans" x="0" y="12" text-anchor="middle" font-size="9" font-weight="700" fill="#A1A1AA" letter-spacing="1.2">SOLVED</text>
    <text class="font-sans" x="0" y="27" text-anchor="middle" font-size="10" font-weight="500" fill="#71717A">{pct_total*100:.1f}%</text>
  </g>

  <!-- Right Column: Breakdown by Difficulty -->
  <g transform="translate(190, 68)">
    <!-- Easy Bar -->
    <g transform="translate(0, 0)">
      <text class="font-sans" x="0" y="10" font-size="11" font-weight="700" fill="#FFFFFF" letter-spacing="0.5">Easy</text>
      <text class="font-sans" x="290" y="10" text-anchor="end" font-size="11" font-weight="600" fill="#F4F4F5">{easy_solved} <tspan fill="#71717A" font-weight="400">/ {easy_total}</tspan></text>
      <rect x="0" y="16" width="290" height="6" rx="3" fill="#27272A" />
      <rect x="0" y="16" width="{w_easy}" height="6" rx="3" fill="#FFFFFF" />
    </g>

    <!-- Medium Bar -->
    <g transform="translate(0, 32)">
      <text class="font-sans" x="0" y="10" font-size="11" font-weight="700" fill="#D4D4D8" letter-spacing="0.5">Medium</text>
      <text class="font-sans" x="290" y="10" text-anchor="end" font-size="11" font-weight="600" fill="#F4F4F5">{medium_solved} <tspan fill="#71717A" font-weight="400">/ {medium_total}</tspan></text>
      <rect x="0" y="16" width="290" height="6" rx="3" fill="#27272A" />
      <rect x="0" y="16" width="{w_medium}" height="6" rx="3" fill="#D4D4D8" />
    </g>

    <!-- Hard Bar -->
    <g transform="translate(0, 64)">
      <text class="font-sans" x="0" y="10" font-size="11" font-weight="700" fill="#A1A1AA" letter-spacing="0.5">Hard</text>
      <text class="font-sans" x="290" y="10" text-anchor="end" font-size="11" font-weight="600" fill="#F4F4F5">{hard_solved} <tspan fill="#71717A" font-weight="400">/ {hard_total}</tspan></text>
      <rect x="0" y="16" width="290" height="6" rx="3" fill="#27272A" />
      <rect x="0" y="16" width="{w_hard}" height="6" rx="3" fill="#71717A" />
    </g>
  </g>

  <!-- Bottom Metric Badges Row -->
  <g transform="translate(190, 168)">
    <!-- Acceptance Rate -->
    <g transform="translate(0, 0)">
      <rect x="0" y="0" width="90" height="34" rx="6" fill="#121215" stroke="#27272A" stroke-width="1" />
      <text class="font-sans" x="45" y="12" text-anchor="middle" font-size="8" font-weight="600" fill="#71717A" letter-spacing="0.5">ACCEPTANCE</text>
      <text class="font-sans" x="45" y="27" text-anchor="middle" font-size="12" font-weight="700" fill="#FFFFFF">{acceptance_rate}</text>
    </g>

    <!-- Global Rank -->
    <g transform="translate(98, 0)">
      <rect x="0" y="0" width="94" height="34" rx="6" fill="#121215" stroke="#27272A" stroke-width="1" />
      <text class="font-sans" x="47" y="12" text-anchor="middle" font-size="8" font-weight="600" fill="#71717A" letter-spacing="0.5">GLOBAL RANK</text>
      <text class="font-sans" x="47" y="27" text-anchor="middle" font-size="11" font-weight="700" fill="#FFFFFF">{ranking}</text>
    </g>

    <!-- Contest Rating / Status -->
    <g transform="translate(200, 0)">
      <rect x="0" y="0" width="90" height="34" rx="6" fill="#121215" stroke="#27272A" stroke-width="1" />
      <text class="font-sans" x="45" y="12" text-anchor="middle" font-size="8" font-weight="600" fill="#71717A" letter-spacing="0.5">CONTEST</text>
      <text class="font-sans" x="45" y="27" text-anchor="middle" font-size="11" font-weight="700" fill="#FFFFFF">{contest}</text>
    </g>
  </g>
</svg>"""
    return svg


def write_svg_file(output_path, svg_content):
    """Safely validate XML and atomically write SVG."""
    # Validate XML before writing
    try:
        ET.fromstring(svg_content)
    except ET.ParseError as e:
        print(f"[ERROR] Generated SVG is not valid XML: {e}")
        return False

    try:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        tmp_path = output_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(svg_content)
        os.replace(tmp_path, output_path)
        print(f"[SUCCESS] Wrote SVG card to {output_path}")
        return True
    except Exception as e:
        print(f"[ERROR] Failed writing SVG to {output_path}: {e}")
        return False


def update_readme_markers(readme_path, stats):
    """Replace content between <!-- LEETCODE:START --> and <!-- LEETCODE:END --> in README.md."""
    if not os.path.isfile(readme_path):
        print(f"[INFO] README file not found at {readme_path}. Skipping README update.")
        return False

    try:
        with open(readme_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"[WARN] Could not read {readme_path}: {e}")
        return False

    start_marker = "<!-- LEETCODE:START -->"
    end_marker = "<!-- LEETCODE:END -->"

    pattern = re.compile(rf"{re.escape(start_marker)}.*?{re.escape(end_marker)}", re.DOTALL)
    if not pattern.search(content):
        print(f"[INFO] Markers '{start_marker}' ... '{end_marker}' not present in {readme_path}. Skipping.")
        return False

    username = stats.get("username", "james719-code")
    total_solved = stats.get("total_solved", 0)
    total_questions = stats.get("total_questions", 3340)
    pct = (total_solved / max(1, total_questions)) * 100
    acceptance = stats.get("acceptance_rate", "0.0%")
    ranking = stats.get("ranking", "N/A")
    contest = stats.get("contest_rating", "Unrated")

    replacement_block = f"""{start_marker}
<div align="center">
  <a href="https://leetcode.com/u/{username}/" target="_blank" rel="noopener noreferrer">
    <img src="assets/leetcode-stats.svg" alt="LeetCode Stats - @{username}" width="520" />
  </a>
  <br/>
  <p>
    <b>Problems Solved:</b> {total_solved}/{total_questions} ({pct:.1f}%) &nbsp;&bull;&nbsp;
    <b>Acceptance:</b> {acceptance} &nbsp;&bull;&nbsp;
    <b>Ranking:</b> {ranking} &nbsp;&bull;&nbsp;
    <b>Contest Rating:</b> {contest}
  </p>
</div>
{end_marker}"""

    updated_content = pattern.sub(replacement_block, content)

    try:
        tmp_readme = readme_path + ".tmp"
        with open(tmp_readme, "w", encoding="utf-8") as f:
            f.write(updated_content)
        os.replace(tmp_readme, readme_path)
        print(f"[SUCCESS] Updated LeetCode section in {readme_path}")
        return True
    except Exception as e:
        print(f"[ERROR] Failed writing updated README to {readme_path}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Fetch LeetCode stats and generate SVG card.")
    parser.add_argument(
        "--username",
        default=os.environ.get("LEETCODE_USERNAME", "james719-code"),
        help="LeetCode username (default: env LEETCODE_USERNAME or 'james719-code')",
    )
    parser.add_argument(
        "--output",
        default="assets/leetcode-stats.svg",
        help="Path for generated SVG card (default: assets/leetcode-stats.svg)",
    )
    parser.add_argument(
        "--cache",
        default="assets/leetcode-cache.json",
        help="Path for JSON cache (default: assets/leetcode-cache.json)",
    )
    parser.add_argument(
        "--readme",
        default="README.md",
        help="Path to README.md file (default: README.md)",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Force use of mock dataset without network queries",
    )
    args = parser.parse_args()

    # Step 1: Fetch stats
    stats = fetch_stats(args.username, cache_path=args.cache, force_mock=args.mock)

    # Step 2: Generate SVG
    svg_content = generate_leetcode_svg(stats)

    # Step 3: Write SVG file
    svg_success = write_svg_file(args.output, svg_content)
    if not svg_success:
        print("[ERROR] SVG generation failed.")
        sys.exit(1)

    # Step 4: Update README if markers exist
    update_readme_markers(args.readme, stats)

    print("[SUCCESS] LeetCode update process complete.")


if __name__ == "__main__":
    main()
