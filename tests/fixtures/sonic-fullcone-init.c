/* One shared expression for ip, ip6 and inet NAT tables. Other table
 * families must not acquire conntrack references through this frontend.
 */
static int nft_fullcone_init(const struct nft_ctx *ctx,
			     const struct nft_expr *expr,
			     const struct nlattr * const tb[])
{
	switch (ctx->family) {
	case NFPROTO_IPV4:
	case NFPROTO_IPV6:
	case NFPROTO_INET:
		return nft_masq_init(ctx, expr, tb);
	default:
		return -EOPNOTSUPP;
	}
}

static int nft_fullcone_validate(const struct nft_ctx *ctx,
				 const struct nft_expr *expr)
{
