#define PRAMA_RUNTIME_IMPL
#include "runtime.h"
#define MAIN
#define exit prama_exit
#include "sctk.h"
#undef exit
#include "bridge.h"
#include <errno.h>

struct ScliteContext { char error[2048]; };
struct ScliteResult { SCORES *scores; PramaArena arena; char *encoding, *language_profile; };
static PRAMA_TLS int in_operation;
static PRAMA_TLS ScliteCallback callback;
static PRAMA_TLS void *callback_data;
static PRAMA_TLS ScliteResult *active_result;
extern int TEXT_set_lang_prof(char *);

ScliteContext *sclite_context_new(void) { return calloc(1, sizeof(ScliteContext)); }
void sclite_context_free(ScliteContext *ctx) { free(ctx); }
const char *sclite_context_error(ScliteContext *ctx) { return ctx ? ctx->error : "invalid context"; }
void sclite_options_init(ScliteOptions *o) {
    if (!o) return;
    memset(o,0,sizeof(*o)); o->version=1; o->struct_size=sizeof(*o);
    o->title="memory"; o->id_type=5; o->left_to_right=1;
}
static int fail(ScliteContext *c, const char *s) {
    if(c) snprintf(c->error,sizeof(c->error),"%s",s);
    return -1;
}
static int write_input(FILE *f,const char *p,size_t n) {
    if (fwrite(p,1,n,f)!=n || fflush(f)!=0) return -1;
    return 0;
}
void prama_notify(void *scores,int g) {
    if (!callback) return;
    active_result->scores=scores;
    if (callback(callback_data,active_result,g,active_result->scores->grp[g].num_path-1))
        prama_exit(2);
}
int sclite_align_texts(ScliteContext *c,const char *r,size_t nr,int rf,const char *h,size_t nh,int hf,const ScliteOptions *o,ScliteResult **out) {
    return sclite_align_texts_stream(c,r,nr,rf,h,nh,hf,o,NULL,NULL,out);
}
int sclite_align_texts_stream(ScliteContext *c,const char *r,size_t nr,int rf,const char *h,size_t nh,int hf,const ScliteOptions *opt,ScliteCallback cb,void *user,ScliteResult **out) {
    if(out) *out=NULL;
    if(!c || !out || !r || !h) return fail(c,"invalid arguments");
    c->error[0]=0;
    ScliteOptions defaults; sclite_options_init(&defaults);
    const ScliteOptions *o=opt ? opt : &defaults;
    if(o->version!=1 || o->struct_size!=sizeof(*o)) return fail(c,"unsupported options ABI");
    if(!((rf==1&&hf==1)||(rf==2&&hf==3)||(rf==3&&hf==3))) return fail(c,"unsupported format combination (TRN/TRN, STM/CTM, CTM/CTM supported)");
    if(o->id_type<1 || o->id_type>6) return fail(c,"invalid id_type");
    if(o->lm_path) return fail(c,"language model support is not compiled in");
    if(o->infer_word_seg<0 || o->infer_word_seg>2 || (o->infer_word_seg && !o->lexicon_path)) return fail(c,"invalid inferred segmentation options");
    if(o->time_align && !(rf==3&&hf==3)) return fail(c,"time alignment requires CTM/CTM");
    if((o->reduce_ref_segments||o->reduce_hyp_words) && rf!=2) return fail(c,"segment reduction requires STM/CTM");
    if(o->char_align_flags<0 || (o->char_align_flags & ~7)) return fail(c,"invalid character alignment flags");
    if(rf==3 && (o->char_align_flags||o->infer_word_seg)) return fail(c,"character/inferred alignment is unsupported for CTM/CTM");
    if(o->wwl_path && (o->time_align||o->char_align_flags||o->infer_word_seg)) return fail(c,"incompatible word weight options");
    if(memchr(r,0,nr)||memchr(h,0,nh)) return fail(c,"embedded NUL in input");
    if(nr>INT_MAX || nh>INT_MAX) return fail(c,"input exceeds native size limit");
    FILE *ref=tmpfile(), *hyp=tmpfile();
    if(!ref||!hyp) { if(ref) fclose(ref); if(hyp) fclose(hyp); return fail(c,"cannot create temporary input"); }
    if(write_input(ref,r,nr)||write_input(hyp,h,nh)) { fclose(ref); fclose(hyp); return fail(c,"cannot write temporary input"); }
    char rp[64],hp[64];
    snprintf(rp,sizeof(rp),"/proc/self/fd/%d",fileno(ref));
    snprintf(hp,sizeof(hp),"/proc/self/fd/%d",fileno(hyp));
    ScliteResult *res=calloc(1,sizeof(*res));
    if(!res) { fclose(ref); fclose(hyp); return fail(c,"out of memory"); }
    if (in_operation) { free(res); fclose(ref); fclose(hyp); return fail(c,"recursive native call from a callback is unsupported"); }
    in_operation = 1;
    prama_reset(); prama_arena=&res->arena;
    callback=cb; callback_data=user; active_result=res;
    int status=setjmp(prama_jump);
    if(!status) {
        res->encoding=prama_strdup(o->encoding ? o->encoding : "ASCII");
        res->language_profile=prama_strdup(o->language_profile ? o->language_profile : "generic");
        if(o->encoding && !TEXT_set_encoding((char *)o->encoding)) prama_exit(3);
        if(o->language_profile && !TEXT_set_lang_prof((char *)o->language_profile)) prama_exit(4);
        WWL *wwl=NULL;
        if(o->wwl_path && load_WWL(&wwl,(TEXT *)o->wwl_path)) prama_exit(5);
        if(wwl) wwl->curw=0;
        char *title=(char *)(o->title ? o->title : "memory");
        if(rf==1) res->scores=align_trans_mode_dp(rp,hp,title,1,o->case_sensitive,o->feedback,o->char_align_flags,o->id_type-1,o->infer_word_seg,(char *)o->lexicon_path,o->fragment_correct,o->optional_deletion,o->infer_flags,wwl,NULL);
        else if(rf==2) res->scores=align_ctm_to_stm_dp(rp,hp,title,1,o->case_sensitive,o->feedback,o->char_align_flags,o->id_type-1,o->infer_word_seg,(char *)o->lexicon_path,o->fragment_correct,o->optional_deletion,o->infer_flags,o->reduce_ref_segments,o->reduce_hyp_words,o->left_to_right,wwl,NULL);
        else res->scores=align_ctm_to_ctm(hp,rp,title,o->feedback,o->fragment_correct,o->optional_deletion,o->case_sensitive,o->time_align,o->left_to_right,wwl,NULL);
        if(!res->scores) prama_exit(1);
    }
    callback=NULL; callback_data=NULL; active_result=NULL;
    if(status) prama_arena_clear(&res->arena);
    in_operation = 1;
    prama_reset(); prama_arena=NULL;
    in_operation = 0;
    fclose(ref); fclose(hyp);
    if(status) { free(res); return fail(c,status==2 ? "alignment cancelled" : status==3 ? "invalid encoding" : status==4 ? "invalid language profile" : "sclite alignment failed"); }
    *out=res; return 0;
}
void sclite_result_free(ScliteResult *r) {
    if(!r) return;
    prama_arena_clear(&r->arena);
    free(r);
}
static void finish_counts(ScliteCounts *c) {
    c->ref_words=c->correct+c->substitutions+c->deletions;
    c->hyp_words=c->correct+c->substitutions+c->insertions;
    c->wer=pct(c->substitutions+c->deletions+c->insertions,c->ref_words);
    c->accuracy=100.0-c->wer;
}
static void add_group(ScliteCounts *c, GRP *g) {
    c->correct+=g->corr; c->substitutions+=g->sub; c->deletions+=g->del; c->insertions+=g->ins;
    c->sentence_count+=g->nsent; c->sentence_errors+=g->serr;
}
int sclite_result_summary(ScliteResult *r,ScliteCounts *c) {
    if(!r||!r->scores||!c) return -1;
    memset(c,0,sizeof(*c));
    for(int i=0;i<r->scores->num_grp;i++) add_group(c,&r->scores->grp[i]);
    finish_counts(c); return 0;
}
int sclite_result_group_count(ScliteResult *r) { return r&&r->scores ? r->scores->num_grp : -1; }
static GRP *group(ScliteResult *r,int i) { return r&&r->scores&&i>=0&&i<r->scores->num_grp ? &r->scores->grp[i] : NULL; }
static PATH *path(ScliteResult *r,int g,int u) { GRP *p=group(r,g); return p&&u>=0&&u<p->num_path ? p->path[u] : NULL; }
int sclite_result_group_summary(ScliteResult *r,int i,const char **name,ScliteCounts *c) {
    GRP *g=group(r,i); if(!g||!name||!c) return -1;
    *name=g->name; memset(c,0,sizeof(*c)); add_group(c,g); finish_counts(c); return 0;
}
int sclite_result_utterance_count(ScliteResult *r,int g) { GRP *p=group(r,g); return p ? p->num_path : -1; }
int sclite_result_utterance(ScliteResult *r,int g,int u,ScliteUtterance *v) {
    PATH *p=path(r,g,u); if(!p||!v) return -1;
    *v=(ScliteUtterance){p->id,p->labels,p->file,p->channel,p->ref_t1,p->ref_t2,p->hyp_t1,p->hyp_t2,p->num}; return 0;
}
int sclite_result_token(ScliteResult *r,int g,int u,int t,ScliteToken *v) {
    PATH *p=path(r,g,u); if(!p||!v||t<0||t>=p->num) return -1;
    PATH_SET *s=&p->pset[t]; WORD *a=s->a_ptr,*b=s->b_ptr;
    *v=(ScliteToken){s->eval,a?(char *)a->value:NULL,b?(char *)b->value:NULL,a?a->T1:0,a?a->T2:0,b?b->T1:0,b?b->T2:0,a?a->conf:0,b?b->conf:0,a?a->weight:0,b?b->weight:0}; return 0;
}
int sclite_result_report_text(ScliteContext *c,ScliteResult *r,int type,char **out,size_t *len) {
    if(out) *out=NULL;
    if(len) *len=0;
    if(!r||!r->scores||!out||!len||type<1||type>5) return fail(c,"invalid report arguments");
    FILE *fp=tmpfile(); if(!fp) return fail(c,"cannot create report stream");
    PramaArena *scratch=calloc(1,sizeof(*scratch));
    if(!scratch) { fclose(fp); return fail(c,"out of memory"); }
    if (in_operation) { free(scratch); fclose(fp); return fail(c,"recursive native call from a callback is unsupported"); }
    in_operation = 1;
    prama_reset(); prama_arena=scratch; prama_report_output=fp;
    int status=setjmp(prama_jump);
    if(!status) {
        TEXT_set_encoding(r->encoding);
        TEXT_set_lang_prof(r->language_profile);
        if(type<=2) print_system_summary(r->scores,"-",0,type==2,0,0);
        else if(type<=4) dump_SCORES_alignments(r->scores,fp,1000,type==4);
        else dump_SCORES_sgml(r->scores,fp,(TEXT *)":",(TEXT *)",");
    }
    prama_arena_clear(scratch); free(scratch); prama_reset(); prama_arena=NULL;
    in_operation = 0;
    if(!status && !fflush(fp) && !fseek(fp,0,SEEK_END)) {
        long n=ftell(fp);
        if(n>=0 && !fseek(fp,0,SEEK_SET)) {
            char *p=malloc((size_t)n+1);
            if(p) { if(fread(p,1,n,fp)==(size_t)n) { p[n]=0; *out=p; *len=n; } else free(p); }
        }
    }
    fclose(fp);
    return *out ? 0 : fail(c,"report generation failed");
}
void sclite_free_string(char *p) { free(p); }
