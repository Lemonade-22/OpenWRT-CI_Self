/* Exercise the kernel frontend with a guard page after its attribute table. */
#include <assert.h>
#include <errno.h>
#include <sys/mman.h>
#include <unistd.h>
#include <stddef.h>
#define NFPROTO_IPV4 2
#define NFPROTO_IPV6 10
#define NFPROTO_INET 1
enum { NFTA_FULLCONE_UNSPEC, NFTA_FULLCONE_FLAGS,
       NFTA_FULLCONE_REG_PROTO_MIN, NFTA_FULLCONE_REG_PROTO_MAX };
enum { NFTA_MASQ_UNSPEC, NFTA_MASQ_FLAGS, NFTA_MASQ_REG_PROTO_MIN,
       NFTA_MASQ_REG_PROTO_MAX, NFTA_MASQ_REG_FULLCONE, NFTA_MASQ_MAX = 4 };
struct nlattr { int value; };
struct nft_ctx { int family; };
struct nft_expr { int unused; };
static const struct nlattr flags = { 7 }, min = { 1024 }, max = { 65535 };
static int calls, result;
static int nft_masq_init(const struct nft_ctx *ctx,
                        const struct nft_expr *expr,
                        const struct nlattr * const tb[])
{
    (void)ctx; (void)expr;
    /* This is the extra read made by the pinned OPhub implementation. */
    assert(tb[NFTA_MASQ_REG_FULLCONE] == NULL);
    assert(tb[NFTA_MASQ_FLAGS] == &flags);
    assert(tb[NFTA_MASQ_REG_PROTO_MIN] == &min);
    assert(tb[NFTA_MASQ_REG_PROTO_MAX] == &max);
    calls++;
    return result;
}
/* INSERT_KERNEL_INIT */
int main(void)
{
    long page = sysconf(_SC_PAGESIZE);
    char *area = mmap(NULL, 2 * page, PROT_READ | PROT_WRITE,
                      MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    assert(area != MAP_FAILED);
    assert(mprotect(area + page, page, PROT_NONE) == 0);
    const struct nlattr **tb = (void *)(area + page - 4 * sizeof(*tb));
    tb[0] = NULL; tb[1] = &flags; tb[2] = &min; tb[3] = &max;
    int families[] = { NFPROTO_IPV4, NFPROTO_IPV6, NFPROTO_INET };
    struct nft_expr expr = { 0 };
    for (int i = 0; i < 3; i++) {
        struct nft_ctx ctx = { families[i] };
        result = 0;
        assert(nft_fullcone_init(&ctx, &expr, tb) == 0);
        result = -EINVAL;
        assert(nft_fullcone_init(&ctx, &expr, tb) == -EINVAL);
    }
    struct nft_ctx unsupported = { 7 };
    assert(nft_fullcone_init(&unsupported, &expr, tb) == -EOPNOTSUPP);
    assert(calls == 6);
    assert(munmap(area, 2 * page) == 0);
    return 0;
}
