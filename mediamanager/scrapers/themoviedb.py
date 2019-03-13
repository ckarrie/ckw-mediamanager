from collections import OrderedDict

import tmdb3
tmdb3.set_key("2b23f9b92ea22e3dbd8903f39f8d5921")


def scrape_show(show_id, language='de'):
    results = OrderedDict()
    tmdb3.set_locale(language)
    tmdb3.set_cache('null')
    show = tmdb3.Series(show_id)
    for season_nr, season in show.seasons.items():
        print "S", season_nr, season.name
        results[season_nr] = OrderedDict()
        for ep_nr, ep in season.episodes.items():
            print " - ", ep_nr, ep.name
            results[season_nr][ep_nr] = ep.name

    return results


#scrape_show(61431)
