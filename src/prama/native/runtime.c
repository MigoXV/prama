#define PRAMA_RUNTIME_IMPL
#include "runtime.h"
#include <errno.h>

union PramaAllocation {
    max_align_t alignment;
    struct { PramaAllocation *next, *prev; PramaArena *owner; size_t size; } h;
};
struct PramaFile { FILE *fp; PramaFile *next; };
PRAMA_TLS PramaArena *prama_arena;
PRAMA_TLS jmp_buf prama_jump;
PRAMA_TLS FILE *prama_report_output;

int prama_array_bytes(ptrdiff_t count, size_t size) {
    if (count < 0 || (size && (size_t)count > INT_MAX / size)) prama_exit(1);
    return (int)((size_t)count * size);
}
void *prama_malloc(size_t n) {
    if (n > SIZE_MAX - sizeof(PramaAllocation)) prama_exit(1);
    PramaAllocation *p = malloc(sizeof(*p) + (n ? n : 1));
    if (!p) prama_exit(1);
    p->h = (typeof(p->h)){prama_arena->memory, NULL, prama_arena, n};
    if (p->h.next) p->h.next->h.prev = p;
    prama_arena->memory = p;
    return p + 1;
}
void prama_free(void *v) {
    if (!v) return;
    PramaAllocation *p = (PramaAllocation *)v - 1;
    if (p->h.prev) p->h.prev->h.next = p->h.next;
    else p->h.owner->memory = p->h.next;
    if (p->h.next) p->h.next->h.prev = p->h.prev;
    free(p);
}
void *prama_calloc(size_t n, size_t s) {
    if (s && n > SIZE_MAX / s) prama_exit(1);
    void *p = prama_malloc(n*s); memset(p, 0, n*s); return p;
}
void *prama_realloc(void *v, size_t n) {
    if (!v) return prama_malloc(n);
    if (!n) { prama_free(v); return NULL; }
    size_t old = ((PramaAllocation *)v - 1)->h.size;
    void *p = prama_malloc(n); memcpy(p, v, old < n ? old : n); prama_free(v); return p;
}
char *prama_strdup(const char *s) {
    size_t n = strlen(s)+1; char *p = prama_malloc(n); memcpy(p,s,n); return p;
}
FILE *prama_fopen(const char *name, const char *mode) {
    PramaFile *f = malloc(sizeof(*f));
    if (!f) prama_exit(1);
    FILE *fp = fopen(name,mode);
    if (!fp) { free(f); return NULL; }
    *f = (PramaFile){fp,prama_arena->files}; prama_arena->files = f; return fp;
}
int prama_fclose(FILE *fp) {
    PramaFile **p = &prama_arena->files;
    while (*p && (*p)->fp != fp) p = &(*p)->next;
    if (*p) { PramaFile *f=*p; *p=f->next; free(f); }
    return fclose(fp);
}
_Noreturn void prama_exit(int code) { longjmp(prama_jump, code ? code : 1); }
void prama_arena_clear(PramaArena *a) {
    while (a->files) { PramaFile *f=a->files; a->files=f->next; fclose(f->fp); free(f); }
    while (a->memory) prama_free(a->memory+1);
}
#define RESET(name) extern void prama_reset_##name(void); prama_reset_##name();
void prama_reset(void) {
    RESET(align) RESET(text) RESET(net_adt) RESET(net_dp) RESET(rpg)
    RESET(path) RESET(stm) RESET(cores)
    prama_report_output = NULL;
}
