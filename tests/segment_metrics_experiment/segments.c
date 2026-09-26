/* Experimental sorted, disjoint half-open interval scan. No allocation/state. */
#include <stddef.h>
#include <stdint.h>

ptrdiff_t segment_hits(const ptrdiff_t *source, ptrdiff_t ns,
                       const ptrdiff_t *target, ptrdiff_t nt,
                       double threshold, int positive_overlap) {
    ptrdiff_t count = 0, first = 0;
    for (ptrdiff_t i = 0; i < ns; ++i) {
        ptrdiff_t start = source[2*i], end = source[2*i+1];
        /* Preserve original any(0 / length >= 0): even disjoint targets hit. */
        if (!positive_overlap && threshold == 0.0 && nt > 0) {
            ++count;
            continue;
        }
        while (first < nt && target[2*first+1] <= start) ++first;
        for (ptrdiff_t j = first; j < nt && target[2*j] < end; ++j) {
            ptrdiff_t left = start > target[2*j] ? start : target[2*j];
            ptrdiff_t right = end < target[2*j+1] ? end : target[2*j+1];
            ptrdiff_t overlap = right > left ? right-left : 0;
            if (positive_overlap ? overlap > 0 :
                (double)overlap / (double)(end-start) >= threshold) {
                ++count;
                break;
            }
        }
    }
    return count;
}
