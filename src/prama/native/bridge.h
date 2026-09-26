#ifndef PRAMA_BRIDGE_H
#define PRAMA_BRIDGE_H
#include <stddef.h>
#define API __attribute__((visibility("default")))
typedef struct {
    int version, struct_size;
    const char *title;
    int id_type;
    const char *encoding, *language_profile;
    int case_sensitive, char_align_flags, fragment_correct, optional_deletion;
    int time_align, left_to_right, infer_word_seg;
    const char *lexicon_path;
    int infer_flags, reduce_ref_segments, reduce_hyp_words;
    const char *wwl_path, *lm_path;
    int feedback;
} ScliteOptions;
typedef struct {
    int ref_words, hyp_words, correct, substitutions, deletions, insertions;
    int sentence_count, sentence_errors;
    double wer, accuracy;
} ScliteCounts;
typedef struct {
    const char *id, *labels, *file, *channel;
    double ref_start, ref_end, hyp_start, hyp_end;
    int token_count;
} ScliteUtterance;
typedef struct {
    int eval;
    const char *ref_word, *hyp_word;
    double ref_start, ref_end, hyp_start, hyp_end;
    double ref_conf, hyp_conf, ref_weight, hyp_weight;
} ScliteToken;
typedef struct ScliteContext ScliteContext;
typedef struct ScliteResult ScliteResult;
/* Borrowed result is valid ONLY during callback; return nonzero to cancel. */
typedef int (*ScliteCallback)(void *, ScliteResult *, int, int);
API ScliteContext *sclite_context_new(void);
API void sclite_context_free(ScliteContext *);
API const char *sclite_context_error(ScliteContext *);
API void sclite_options_init(ScliteOptions *);
API int sclite_align_texts(ScliteContext *, const char *, size_t, int, const char *, size_t, int, const ScliteOptions *, ScliteResult **);
API int sclite_align_texts_stream(ScliteContext *, const char *, size_t, int, const char *, size_t, int, const ScliteOptions *, ScliteCallback, void *, ScliteResult **);
API void sclite_result_free(ScliteResult *);
API int sclite_result_summary(ScliteResult *, ScliteCounts *);
API int sclite_result_group_count(ScliteResult *);
API int sclite_result_group_summary(ScliteResult *, int, const char **, ScliteCounts *);
API int sclite_result_utterance_count(ScliteResult *, int);
API int sclite_result_utterance(ScliteResult *, int, int, ScliteUtterance *);
API int sclite_result_token(ScliteResult *, int, int, int, ScliteToken *);
API int sclite_result_report_text(ScliteContext *, ScliteResult *, int, char **, size_t *);
API void sclite_free_string(char *);
#endif
