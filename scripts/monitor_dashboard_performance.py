# scripts/monitor_dashboard_performance.py
"""
Script to monitor dashboard endpoint performance.

This script demonstrates how to:
1. Test the new divided endpoints
2. Compare performance with original endpoint
3. Monitor cache effectiveness
4. Generate performance reports
"""

import time
import json
from typing import Dict, List
from datetime import datetime

try:
    import requests
except ImportError:
    print("❌ 'requests' module not found. Install with: pip install requests")
    exit(1)

# Configuration
BASE_URL = "http://localhost:8001/api/v1"
ENDPOINTS = [
    "/teacher/dashboard/stats",
    "/teacher/dashboard/recent-documents", 
    "/teacher/dashboard/recent-lectures",
    "/teacher/dashboard",  # Original endpoint for comparison
    "/teacher/dashboard/performance",  # Performance metrics
]

def test_endpoint(endpoint: str) -> Dict:
    """Test a single endpoint and return performance metrics."""
    url = f"{BASE_URL}{endpoint}"
    
    # Measure response time
    start_time = time.perf_counter()
    
    try:
        response = requests.get(url, timeout=10)
        end_time = time.perf_counter()
        
        return {
            "endpoint": endpoint,
            "status_code": response.status_code,
            "response_time_ms": (end_time - start_time) * 1000,
            "content_length": len(response.content),
            "success": response.status_code == 200,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        end_time = time.perf_counter()
        return {
            "endpoint": endpoint,
            "status_code": 0,
            "response_time_ms": (end_time - start_time) * 1000,
            "content_length": 0,
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

def run_performance_test(iterations: int = 3):
    """Run performance tests on all dashboard endpoints."""
    print(f"🚀 Running performance test with {iterations} iterations...")
    print("=" * 60)
    
    results = []
    
    for i in range(iterations):
        print(f"\n📊 Iteration {i + 1}/{iterations}")
        
        # Test all endpoints
        iteration_results = []
        for endpoint in ENDPOINTS:
            result = test_endpoint(endpoint)
            iteration_results.append(result)
            
            # Display result
            status = "✅" if result["success"] else "❌"
            time_ms = result["response_time_ms"]
            print(f"  {status} {result['endpoint']}: {time_ms:.0f}ms")
        
        results.extend(iteration_results)
        
        # Wait between iterations to test caching
        if i < iterations - 1:
            print("⏳ Waiting 2 seconds to test caching...")
            time.sleep(2)
    
    return results

def analyze_results(results: List[Dict]):
    """Analyze performance test results."""
    print("\n" + "=" * 60)
    print("📈 PERFORMANCE ANALYSIS")
    print("=" * 60)
    
    # Group results by endpoint
    endpoint_stats = {}
    for result in results:
        endpoint = result["endpoint"]
        if endpoint not in endpoint_stats:
            endpoint_stats[endpoint] = []
        endpoint_stats[endpoint].append(result)
    
    # Calculate statistics for each endpoint
    for endpoint, endpoint_results in endpoint_stats.items():
        successful_results = [r for r in endpoint_results if r["success"]]
        
        if not successful_results:
            print(f"\n❌ {endpoint}: All requests failed")
            continue
        
        response_times = [r["response_time_ms"] for r in successful_results]
        avg_time = sum(response_times) / len(response_times)
        min_time = min(response_times)
        max_time = max(response_times)
        
        print(f"\n📊 {endpoint}")
        print(f"  ✅ Success Rate: {len(successful_results)}/{len(endpoint_results)} ({len(successful_results)/len(endpoint_results)*100:.0f}%)")
        print(f"  ⚡ Average Time: {avg_time:.0f}ms")
        print(f"  🚀 Min Time: {min_time:.0f}ms") 
        print(f"  🐌 Max Time: {max_time:.0f}ms")
        print(f"  📦 Avg Size: {sum(r['content_length'] for r in successful_results)/len(successful_results):.0f} bytes")
    
    # Compare divided vs consolidated endpoint
    stats_results = endpoint_stats.get("/teacher/dashboard/stats", [])
    consolidated_results = endpoint_stats.get("/teacher/dashboard", [])
    
    if stats_results and consolidated_results:
        stats_avg = sum(r["response_time_ms"] for r in stats_results if r["success"]) / len([r for r in stats_results if r["success"]])
        consolidated_avg = sum(r["response_time_ms"] for r in consolidated_results if r["success"]) / len([r for r in consolidated_results if r["success"]])
        
        print(f"\n🏁 COMPARISON")
        print(f"  📊 Divided endpoints (stats): {stats_avg:.0f}ms avg")
        print(f"  📦 Consolidated endpoint: {consolidated_avg:.0f}ms avg")
        
        if stats_avg < consolidated_avg:
            improvement = ((consolidated_avg - stats_avg) / consolidated_avg) * 100
            print(f"  ✅ Performance improvement: {improvement:.0f}% faster")
        else:
            regression = ((stats_avg - consolidated_avg) / consolidated_avg) * 100  
            print(f"  ⚠️ Performance regression: {regression:.0f}% slower")

def get_cache_performance():
    """Get cache performance metrics."""
    print("\n" + "=" * 60)
    print("💾 CACHE PERFORMANCE")
    print("=" * 60)
    
    try:
        response = requests.get(f"{BASE_URL}/teacher/dashboard/performance", timeout=5)
        if response.status_code == 200:
            data = response.json()
            
            cache_stats = data.get("cache_stats", {})
            print(f"  📊 Cache Size: {cache_stats.get('size', 0)} items")
            print(f"  🎯 Hit Rate: {cache_stats.get('hit_rate', '0%')}")
            print(f"  📈 Hits: {cache_stats.get('hits', 0)}")
            print(f"  ❌ Misses: {cache_stats.get('misses', 0)}")
            print(f"  📦 Max Size: {cache_stats.get('max_size', 0)}")
            
            endpoints = data.get("endpoints", [])
            print(f"\n  🔧 Endpoints monitored: {len(endpoints)}")
            for endpoint in endpoints:
                print(f"    - {endpoint['path']}: {endpoint['cache_ttl']} TTL")
        else:
            print(f"  ❌ Failed to get performance metrics: HTTP {response.status_code}")
    except Exception as e:
        print(f"  ❌ Error getting cache performance: {e}")

def main():
    """Main monitoring script."""
    print("🔍 Dashboard Performance Monitor")
    print("Testing the new divided dashboard endpoints...")
    
    # Run performance tests
    results = run_performance_test(iterations=3)
    
    # Analyze results
    analyze_results(results)
    
    # Get cache performance
    get_cache_performance()
    
    print("\n" + "=" * 60)
    print("✅ Monitoring complete!")
    print("💡 Tips:")
    print("  - Check application logs for detailed performance metrics")
    print("  - Monitor cache hit rates over time")
    print("  - Use the /teacher/dashboard/performance endpoint for real-time stats")
    print("=" * 60)

if __name__ == "__main__":
    main()
