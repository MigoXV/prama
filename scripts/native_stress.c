#include "bridge.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static int cancel(void *u,ScliteResult *r,int g,int i) { return 1; }
int main(int argc,char **argv) {
    int loops=argc>1 ? atoi(argv[1]) : 10000;
    const char *refs[]={"a b c (s_1)\n", "你 好 世界 (s_1)\n", "a b (s_1)\na (s_2)\n"};
    const char *hyps[]={"a x c d (s_1)\n", "你 好 世 (s_1)\n", "a (s_1)\nb (s_2)\n"};
    ScliteContext *c=sclite_context_new(); assert(c);
    for(int j=0;j<loops;j++) {
        ScliteOptions o; sclite_options_init(&o); o.encoding="UTF-8"; o.char_align_flags=j%2;
        int k=j%3; ScliteResult *r=NULL;
        assert(!sclite_align_texts(c,refs[k],strlen(refs[k]),1,hyps[k],strlen(hyps[k]),1,&o,&r));
        ScliteCounts n; assert(!sclite_result_summary(r,&n));
        { int t=1+j%5; char *s;size_t len; assert(!sclite_result_report_text(c,r,t,&s,&len)); assert(len); sclite_free_string(s); }
        sclite_result_free(r);
        assert(sclite_align_texts_stream(c,refs[k],strlen(refs[k]),1,hyps[k],strlen(hyps[k]),1,&o,cancel,NULL,&r)); assert(!r);
        /* Error after allocating and successfully scoring the first record. */
        const char *bad="a (s_1)\nb (missing)\n";
        assert(sclite_align_texts(c,refs[k],strlen(refs[k]),1,bad,strlen(bad),1,&o,&r)); assert(!r);
    }
    sclite_context_free(c); printf("%d success/report/cancel/error cycles passed\n",loops);
}
