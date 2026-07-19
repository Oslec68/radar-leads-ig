create table if not exists radar_leads_ig (
    id bigint generated always as identity primary key,
    username text unique not null,
    nome text,
    bio text,
    seguidores integer,
    verificado boolean,
    categoria_ig text,
    email text,
    telefone text,
    url_perfil text,
    hashtag_origem text,
    coletado_em timestamptz,
    status text default 'novo',
    responsavel text,
    observacoes text
);

create index if not exists idx_radar_leads_hashtag on radar_leads_ig (hashtag_origem);
create index if not exists idx_radar_leads_status on radar_leads_ig (status);
