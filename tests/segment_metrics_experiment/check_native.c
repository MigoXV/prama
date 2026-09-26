/* Standalone sanitizer test; no Python or production code modification. */
#include <assert.h>
#include <stdio.h>
#include "segments.c"

static uint32_t state = 20260926;
static ptrdiff_t generate(ptrdiff_t *out) {
    ptrdiff_t n = 0, start = -1;
    for (ptrdiff_t i = 0; i <= 128; ++i) {
        state = state * 1664525u + 1013904223u;
        int active = i < 128 && (state >> 28) < 8;
        if (active && start < 0) start = i;
        if (!active && start >= 0) {
            out[2*n] = start; out[2*n+1] = i; ++n; start = -1;
        }
    }
    return n;
}
static ptrdiff_t brute(const ptrdiff_t *a, ptrdiff_t na,
                       const ptrdiff_t *b, ptrdiff_t nb, double t, int positive) {
    ptrdiff_t count = 0;
    for (ptrdiff_t i = 0; i < na; ++i) {
        for (ptrdiff_t j = 0; j < nb; ++j) {
            ptrdiff_t left = a[2*i] > b[2*j] ? a[2*i] : b[2*j];
            ptrdiff_t right = a[2*i+1] < b[2*j+1] ? a[2*i+1] : b[2*j+1];
            ptrdiff_t overlap = right > left ? right-left : 0;
            if (positive ? overlap > 0 : (double)overlap/(a[2*i+1]-a[2*i]) >= t) {
                ++count; break;
            }
        }
    }
    return count;
}
int main(void) {
    double thresholds[] = {0.0, 0.5, 0.9, 1.0};
    assert(segment_hits(NULL, 0, NULL, 0, 0.9, 0) == 0);
    for (int k = 0; k < 10000; ++k) {
        ptrdiff_t a[256], b[256];
        ptrdiff_t na = generate(a), nb = generate(b);
        for (int i = 0; i < 4; ++i) {
            assert(segment_hits(a, na, b, nb, thresholds[i], 0) ==
                   brute(a, na, b, nb, thresholds[i], 0));
            assert(segment_hits(b, nb, a, na, thresholds[i], 1) ==
                   brute(b, nb, a, na, thresholds[i], 1));
        }
    }
    puts("10000 cases: exact counts; ASan/UBSan/LSan clean if exit status is zero.");
    return 0;
}
