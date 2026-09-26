#ifndef PRAMA_RUNTIME_H
#define PRAMA_RUNTIME_H
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <stddef.h>
#include <setjmp.h>
#include <unistd.h>
#include <limits.h>
#include <pthread.h>

#define PRAMA_TLS _Thread_local

typedef union PramaAllocation PramaAllocation;
typedef struct PramaFile PramaFile;
typedef struct {
    PramaAllocation *memory;
    PramaFile *files;
} PramaArena;
extern PRAMA_TLS PramaArena *prama_arena;
extern PRAMA_TLS jmp_buf prama_jump;
extern PRAMA_TLS FILE *prama_report_output;
int prama_array_bytes(ptrdiff_t, size_t);
void *prama_malloc(size_t);
void *prama_calloc(size_t, size_t);
void *prama_realloc(void *, size_t);
void prama_free(void *);
char *prama_strdup(const char *);
FILE *prama_fopen(const char *, const char *);
int prama_fclose(FILE *);
_Noreturn void prama_exit(int);
void prama_arena_clear(PramaArena *);
void prama_reset(void);
void prama_notify(void *, int);
#ifndef PRAMA_RUNTIME_IMPL
#define malloc prama_malloc
#define calloc prama_calloc
#define realloc prama_realloc
#define free prama_free
#define strdup prama_strdup
#define fopen prama_fopen
#define fclose prama_fclose
#define exit prama_exit
#endif
#endif
