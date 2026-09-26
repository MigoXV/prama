#include "bridge.h"
#include <assert.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define THREADS 8
static pthread_barrier_t barrier;
static const char *ref="Hello 世界 (s_1)\na b a (s_2)\n";
static const char *hyp="hello 世 (s_1)\na a b (s_2)\n";
static char *expected[THREADS];
static ScliteResult *transferred[THREADS];
static int iterations=100;
typedef struct { int cancel; } CallbackData;
static int notify(void *user,ScliteResult *result,int group,int utterance) {
    ScliteUtterance u;
    assert(!sclite_result_utterance(result,group,utterance,&u));
    assert(u.token_count>0);
    if(utterance==0) pthread_barrier_wait(&barrier);
    return ((CallbackData *)user)->cancel;
}
static ScliteOptions options(int index) {
    ScliteOptions o; sclite_options_init(&o);
    o.encoding="UTF-8";o.case_sensitive=index%2;o.char_align_flags=(index/2)%2;
    return o;
}
static void *worker(void *arg) {
    int index=(int)(size_t)arg;
    ScliteContext *c=sclite_context_new();assert(c);
    ScliteOptions o=options(index);
    for(int j=0;j<iterations;j++) {
        ScliteResult *r=NULL;CallbackData state={index==0 && j%7==0};
        int status=sclite_align_texts_stream(c,ref,strlen(ref),1,hyp,strlen(hyp),1,&o,notify,&state,&r);
        if(state.cancel) { assert(status && !r);continue; }
        assert(!status && r);
        char *text;size_t n;
        assert(!sclite_result_report_text(c,r,3,&text,&n));
        assert(!strcmp(text,expected[index]));sclite_free_string(text);
        if(j==iterations-1) transferred[index]=r;
        else sclite_result_free(r);
    }
    sclite_context_free(c);return NULL;
}
int main(int argc,char **argv) {
    if(argc>1) iterations=atoi(argv[1]);
    ScliteContext *c=sclite_context_new();assert(c);
    for(int i=0;i<THREADS;i++) {
        ScliteOptions o=options(i);ScliteResult *r;size_t n;
        assert(!sclite_align_texts(c,ref,strlen(ref),1,hyp,strlen(hyp),1,&o,&r));
        assert(!sclite_result_report_text(c,r,3,&expected[i],&n));
        sclite_result_free(r);
    }
    pthread_barrier_init(&barrier,NULL,THREADS);
    pthread_t threads[THREADS];
    for(int i=0;i<THREADS;i++) assert(!pthread_create(&threads[i],NULL,worker,(void *)(size_t)i));
    for(int i=0;i<THREADS;i++) assert(!pthread_join(threads[i],NULL));
    for(int i=0;i<THREADS;i++) {
        if(transferred[i]) {
            char *text;size_t n;
            assert(!sclite_result_report_text(c,transferred[i],3,&text,&n));
            assert(!strcmp(text,expected[i]));sclite_free_string(text);
            sclite_result_free(transferred[i]);
        }
        sclite_free_string(expected[i]);
    }
    pthread_barrier_destroy(&barrier);sclite_context_free(c);
    printf("%d threads x %d iterations: alignment, callbacks, cancellation, reports and cross-thread destruction passed\n",THREADS,iterations);
}
