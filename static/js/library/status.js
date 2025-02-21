/* global each, _, echo, url_base, current_page, per_page, pages, movie_sort_direction, movie_sort_key, cached_movies, $page_select, loading_library, $sort_direction_button, $movie_list, $hide_finished_movies_toggle, templates, status_colors, notify_error, $movie_status_modal */
var exp_date = new Date();
exp_date.setFullYear(exp_date.getFullYear() + 10);
exp_date = exp_date.toUTCString();

function read_cookie(){
    /* Read document cookie
    Returns dict
    */
    var dcookie = document.cookie;
    var cookie_obj = {};
    var cookiearray = dcookie.split("; ");

    for (var i = 0; i < cookiearray.length; i++) {
        var key = cookiearray[i].split("=")[0];
        var value = decodeURIComponent(cookiearray[i].split("=")[1]);
        cookie_obj[key] = value;
    }
    return cookie_obj;
}

function set_cookie(k, v){
    /* Helper method to set cookies
    k (str): cookie key
    v (str): cookie value

    Constructs and sets cookie in browser

    Returns cookie string
    */

    var c = `${k}=${encodeURIComponent(v)};path=/;expires=${exp_date}`;

    document.cookie = c;

    return c;
}

function change_page_number(){
    document.querySelector("button#page_count").innerText = "/ " + pages;
    if(pages > 0){
        $page_select.innerHTML = "";
        each(Array(pages), function(item, index){
            $page_select.innerHTML += `<option value="${index + 1}">${index + 1}</option>`;
        });
    } else {
        $page_select.innerHTML = `<option value="">0</option>`;
    }
}

window.addEventListener("DOMContentLoaded", function(){
    current_page = 1;
    per_page = 50;
    var cookie = read_cookie();
    echo.init({
        offsetVertical: 100,
        callback: function(element, op){
            element.style.opacity = 1;
        }
    });

    /* Read cookie vars */
    var movie_layout = (cookie["movie_layout"] || "").split(" ")[0] || "posters";
    movie_sort_direction = cookie["movie_sort_direction"] || "desc";
    movie_sort_key = cookie["movie_sort_key"] || "sort_title";
    var hide_finished_movies = cookie["hide_finished_movies"] || "False";
    if(per_page !== cookie["per_page"]){
        per_page = cookie["per_page"]
    }
    if(movie_sort_key === "status_key"){
        movie_sort_key = "status";
    } else if(movie_sort_key === "title"){
        movie_sort_key = "sort_title";
    }

    var movie_count = parseInt(document.querySelector("meta[name=\"movie_count\"]").content, 10);
    var finished_count = parseInt(document.querySelector("meta[name=\"finished_count\"]").content, 10);
    cached_movies = Array(movie_count);

    $page_select = document.querySelector("select#page_number");
    pages = Math.ceil(movie_count / per_page);

    $page_select.addEventListener("change", function(event){
        current_page = parseInt(event.target.value);
        load_library(movie_sort_key, movie_sort_direction, current_page, per_page, pages);
    });

    $page_select.value = "1";

    loading_library = false; // Indicates that a library ajax request is being executed

    $sort_direction_button = document.querySelector("button#sort_direction > i");
    $movie_list = document.getElementById("movie_list");
    $hide_finished_movies_toggle = document.getElementById("hide_finished_movies");

    templates = {
        movie: document.querySelector("template#template_movie").innerHTML,
        info: document.querySelector("template#template_movie_info").innerHTML,
        delete: document.querySelector("template#template_delete").innerHTML,
        delete_file: document.querySelector("template#template_delete_file").innerHTML,
        release: document.querySelector("template#template_release").innerHTML
    };
    status_colors = {
        Finished: "success",
        Snatched: "primary",
        Found: "warning",
        Bad: "danger",
        Wanted: "wanted",
        Available: "available",
        Waiting: "waiting",
    };

    /* Set sort ui elements off cookie */
    $movie_list.classList = "";
    $movie_list.classList.add(movie_layout);
    document.querySelector(`div#movie_layout > div > button[data-layout="${movie_layout}"]`).classList.add("active");
    document.getElementById("per_page").value = per_page;
    echo.render();

    if(movie_sort_direction === "asc"){
        $sort_direction_button.classList.add("mdi-sort-ascending");
    } else {
        $sort_direction_button.classList.add("mdi-sort-descending");
    }

    document.querySelector(`select#movie_sort_key > option[value=${movie_sort_key}]`).setAttribute("selected", true);
//    document.querySelector(`select#per_page > option[value=${per_page}]`).setAttribute("selected", true)

    if(hide_finished_movies === "True"){
        $hide_finished_movies_toggle.setAttribute("value", "True");
        $hide_finished_movies_toggle.classList.remove("mdi-checkbox-blank-outline");
        $hide_finished_movies_toggle.classList.add("mdi-checkbox-marked");
        cached_movies = Array(movie_count - finished_count)
        pages = Math.ceil((movie_count - finished_count) / per_page);
    } else {
        cached_movies = Array(movie_count)
        pages = Math.ceil((movie_count) / per_page);
    }
    change_page_number();

    /* Finish by loading page 1 */
    load_library(movie_sort_key, movie_sort_direction, 1, per_page, pages);

    /* Toolbar action bindings
        /* per page */
    document.getElementById("movie_sort_key").addEventListener("change", function(event){
        event.preventDefault();
        if(loading_library){
            return false;
        }

        movie_sort_key = event.target.value;

        var reset_cache = false;
        each(cached_movies, function(cm){
            if(cm === undefined){
                reset_cache = true;
                return false;
            }
        });
        if(reset_cache){
            cached_movies = Array(movie_count);
        } else {
            sort_movie_cache(movie_sort_key);
        }
        set_cookie("movie_sort_key", movie_sort_key);

        load_library(movie_sort_key, movie_sort_direction, current_page, per_page, pages);
    });

    /* per page key */
    document.getElementById("per_page").addEventListener("change", function(event){
        event.preventDefault();
        if(loading_library){
            return false
        }

        per_page = event.target.value;

        set_cookie("per_page", per_page);
        var hf = $hide_finished_movies_toggle.getAttribute("value");

        if(hf === "True"){
            cached_movies = Array(movie_count - finished_count);
            pages = Math.ceil((movie_count - finished_count) / per_page);
        } else {
            cached_movies = Array(movie_count);
            pages = Math.ceil((movie_count) / per_page);
        }
        change_page_number();

        load_library(movie_sort_key, movie_sort_direction, current_page, per_page, pages);
    });

    /* Movie sort direction */
    // See fn switch_sort_direction()

    /* Movie layout style */
    each(document.querySelectorAll("div#movie_layout > div > button"), function(button){
        button.addEventListener("click", function(event){
            if(!button.classList.contains("active")){
                var movie_layout = button.dataset.layout;
                each(button.parentElement.children, function(sibling){
                    sibling.classList.remove("active");
                });
                button.classList.add("active");
                $movie_list.classList = "";
                $movie_list.classList.add(movie_layout);
                set_cookie("movie_layout", movie_layout);
                echo.render();
            }
        });

    });

    document.getElementsByTagName("body")[0].addEventListener("click", function(event){
        if(event.target.classList.contains("c_box")){
            var c = event.target;
            if(c.getAttribute("value") === "False"){
                c.setAttribute("value", "True");
                c.classList.remove("mdi-checkbox-blank-outline");
                c.classList.add("mdi-checkbox-marked");
            } else {
                c.setAttribute("value", "False");
                c.classList.remove("mdi-checkbox-marked");
                c.classList.add("mdi-checkbox-blank-outline");
            }
        }
    });

    $hide_finished_movies_toggle.addEventListener("click", function(event){
        var hf;
        if(event.target.getAttribute("value") === "False"){
            set_cookie("hide_finished_movies", "True");
            cached_movies = Array(movie_count - finished_count);
            var pp = document.getElementById("per_page").value;
            pages = Math.ceil((movie_count - finished_count) / pp);
            hf = "True";
        } else {
            set_cookie("hide_finished_movies", "False");
            cached_movies = Array(movie_count);
            var pp = document.getElementById("per_page").value;
            pages = Math.ceil((movie_count) / pp);
            hf = "False";
        }
        change_page_number();
        $page_select.value = 1;
        load_library(movie_sort_key, movie_sort_direction, 1, per_page, pages, hf);
    })

});

function sort_movie_cache(key){
    var forward, backward;
    if(movie_sort_direction === "desc"){
        forward = 1;
        backward = -1;
    } else {
        forward = -1;
        backward = 1;
    }

    cached_movies.sort(function(a, b){
        if(a[key] > b[key]){
            return forward;
        } else if(a[key] < b[key]){
            return backward;
        } else {
            return 0;
        }
    });
}

function load_library(sort_key, sort_direction, page, per_page, pages, hf){
    /* Loads library into DOM
    sort_key: str value with which to sort movies
    sort_direction: str [asc, desc] direction to sort movies
    page: int page number
    hf: str ("True", "False") load hidden/finished movies <optional>

    hf will be read from checkbox in DOM if not passed

    Clears movies from dom and loads new page.
    Checks if all movies are cached and loads them. If not cached requests movies from server.
    */
    if(page === 0){
        return;
    }

    showLoader();
    loading_library = true;

    $movie_list.innerHTML = "";

    var offset = (page * per_page) - per_page;

    var use_cache = true;
    var cached_page = cached_movies.slice(offset, offset + per_page);

    for (var i = 0; i < cached_page.length; i++) {
        if(cached_page[i] === undefined){
            use_cache = false;
            break
        }
    }

    if(hf === undefined){
        hf = $hide_finished_movies_toggle.getAttribute("value");
    }

    if(use_cache){
        _render_library(cached_page);
        loading_library = false;
    } else {
        $.post(url_base + "/ajax/library", {
            "sort_key": sort_key,
            "sort_direction": sort_direction,
            "limit": per_page,
            "offset": offset,
            "hide_finished": hf
        })
        .done(function(response){
            Array.prototype.splice.apply(cached_movies, [offset, response.length].concat(response));
            _render_library(response);

        })
        .fail(notify_error)
        .always(function(){
            loading_library = false;
        });
    }
    hideLoader();
}

function _render_library(movies){
    // Renders movies list items after loading page
    each(movies, function(movie, index){
        var template = templates.movie;
        movie["url_base"] = url_base;

        movie["status_select"] = movie["status"]; // Keep "Disabled" for dropdown

        if(movie["status"] === "Disabled"){
            movie["status"] = "Finished";
        }

        movie["status_color"] = status_colors[movie["status"]];

        movie["media_release_date"] = (movie["media_release_date"] || "Unannounced");

        if(!movie["poster"]){
            movie["poster"] = "missing_poster.jpg";
        }

        movie["status_translated"] = _(movie["status"]);
        $item = format_template(template, movie);

        var score = Math.round(movie["score"]) / 2, i_half_star;
        if(score % 1 === 0.5){
            i_half_star = Math.floor(score);
        }
        each($item.querySelectorAll("span.score > i.mdi"), function(star, index){
            if(index + 1 <= score){
                star.classList.remove("mdi-star-outline");
                star.classList.add("mdi-star");
            } else if(index === i_half_star){
                star.classList.remove("mdi-star-outline");
                star.classList.add("mdi-star-half");
            }

        });
        $item.dataset.movie = JSON.stringify(movie);
        $movie_list.innerHTML += $item.outerHTML;
    });

    echo.init({
        offsetVertical: 100,
        callback: function(element, op){
            element.style.opacity = 1;
        }
    });
}

function change_page_sequential(event, direction){
    // direction: int direction and count of pages to move [-1, 1]
    event.preventDefault();
    if(loading_library){
        return false;
    }

    var page = current_page + direction;

    if(page < 1 || page > pages){
        return false;
    }
    $page_select.value = page;

    load_library(movie_sort_key, movie_sort_direction, page, per_page, pages);
    current_page = page;
}

function switch_sort_direction(event, elem){
    // Change sort direction of movie list
    if(loading_library){
        event.preventDefault();
        return false;
    }

    if($sort_direction_button.classList.contains("mdi-sort-ascending")){
        $sort_direction_button.classList.remove("mdi-sort-ascending");
        $sort_direction_button.classList.add("mdi-sort-descending");
        movie_sort_direction = "desc";
    } else {
        $sort_direction_button.classList.remove("mdi-sort-descending");
        $sort_direction_button.classList.add("mdi-sort-ascending");
        movie_sort_direction = "asc";
    }

    set_cookie("movie_sort_direction", movie_sort_direction);

    cached_movies.reverse();
    reversed_pages = [];

    load_library(movie_sort_key, movie_sort_direction, current_page, per_page, pages);
}

function open_info_modal(event, elem){
    // Generate and show movie info modal
    event.preventDefault();

    var movie = JSON.parse(elem.dataset.movie);
    Object.assign(movie, JSON.parse(movie.filters)); // Merges filters column from db into movies object for templating

    if(movie["origin"] === null){
        movie["origin"] = "";
    }

    var search_results = {};
    var results_table = "";
    $.post(url_base + "/ajax/get_search_results", {
        "imdbid": movie["imdbid"],
        "quality": movie["quality"]
    })
    .done(function(response){
        if(response["response"] === true){
            movie["table"] = _results_table(response["results"]);
        } else {
            movie["table"] = `<li class="search_result list-group-item">
                                  <span>Nothing found yet. Next search scheduled for ${response["next"]}.</span>
                              </li>`;
        }
        var modal = format_template(templates.info, movie);

        movie["title_escape"] = movie["title"].replace(/'/g, "\\'");
        $movie_status_modal = $(modal);

        $movie_status_modal.data("movie", movie);
        $movie_status_modal.find("select#movie_quality > option[value='" + movie["quality"] + "']").attr("selected", true);
        $movie_status_modal.find("select#movie_category > option[value='" + movie["category"] + "']").attr("selected", true);
        $status_select = $movie_status_modal.find("select#movie_status");

        if(movie["status_select"] === "Disabled"){
            $status_select.find("option[value='Disabled']").attr("selected", true)
        } else {
            $status_select.find("option[value='Automatic']").attr("selected", true)
        }

        if(movie["status"] === "Finished" || movie["status"] === "Disabled"){
            $movie_status_modal.find("span#finished_file_badge").removeClass("hidden");
        }

        $movie_status_modal.modal("show");
        $movie_status_modal.on("hidden.bs.modal", function(){
            this.parentNode.removeChild(this);
        })

    })
    .fail(notify_error);
}

function _results_table(results){
    /* Generate search results table for modal
    results: list of dicts of result info
    */

    rows = "";
    each(results, function(result, index){
        if(result["freeleech"] >= 1){
            result["fl"] = `<span class="label label-default" title="Freeleech: ${result["freeleech"]}"><i class="mdi mdi-heart"></i></span>`
        } else if(result["freeleech"] > 0 && result["freeleech"] < 1){
            result["fl"] = `<span class="label label-default" title="Freeleech: ${result["freeleech"]}"><i class="mdi mdi-heart-half-full"></i></span>`
        } else {
            result["fl"] = "";
        }

        result["translated_status"] = _(result["status"]);
        result["status_color"] = status_colors[result["status"]];
        result["guid"] = result["guid"].replace(/'/g, "\\'");
        rows += format_template(templates.release, result).outerHTML;
    });

    return rows;
}

function manual_search(event, button, imdbid){
    var $i = button.querySelector("i.mdi");

    $i.classList.remove("mdi-magnify");
    $i.classList.add("mdi-circle");
    $i.classList.add("animated");

    var $search_results_table = document.getElementById("search_results_table");
    var orig_maxHeight = getComputedStyle($search_results_table).maxHeight;
    $search_results_table.style.overflowY = "hidden";
    $search_results_table.style.maxHeight = "0px";

    var table = "";

    $.post(url_base + "/ajax/search", {"imdbid": imdbid})
    .done(function(response){
        if(response["response"] === true && response["results"].length > 0){
            $search_results_table.innerHTML = _results_table(response["results"]);
        } else if(response["response"] === true && response["results"].length === 0){
            table = `<div class="search_result list-group-item">
                         <span>Nothing found yet. Next search scheduled for ${response["next"]}.</span>
                     </div>`;
            $search_results_table.innerHTML = table;
        } else {
            $.notify({message: response["error"]}, {type: "danger"});
        }
        if(response["movie_status"]){
            update_movie_status(imdbid, response["movie_status"]);
        }
    })
    .fail(notify_error)
    .always(function(){
        $search_results_table.style.maxHeight = orig_maxHeight;
        $i.classList.remove("mdi-circle");
        $i.classList.add("mdi-magnify");
        $i.classList.remove("animated");
        $search_results_table.style.overflowY = "scroll";
    });
}

function update_metadata(event, elem, imdbid, tmdbid){
    event.preventDefault();

    var $i = elem.querySelector("i.mdi");
    $i.classList.remove("mdi-tag-text-outline");
    $i.classList.add("mdi-circle");
    $i.classList.add("animated");

    $.post(url_base + "/ajax/update_metadata", {
        "imdbid": imdbid,
        "tmdbid": tmdbid
    })
    .done(function(response){
        if(response["response"] === true){
            $.notify({message: response["message"]});
        } else {
            $.notify({message: response["error"]}, {type: "danger"});
        }
    })
    .fail(notify_error)
    .always(function(){
        $i.classList.remove("mdi-circle");
        $i.classList.remove("animated");
        $i.classList.add("mdi-tag-text-outline");
    });
}

function remove_movie(event, elem, imdbid){
    event.preventDefault();

    var movie = $movie_status_modal.data("movie");

    var modal = format_template(templates.delete, movie);
    $delete = $(modal);

    if(!movie["finished_file"]){
        $delete.find("div#delete_file").hide();
    }

    $delete.modal("show");
    $movie_status_modal.css("opacity", 0);
    $delete.on("hide.bs.modal", function(){
        $movie_status_modal.css("opacity", 1);
        $delete.remove();
    });
}

function _remove_movie(event, elem, imdbid){
    /* Removes movie from library
    imdbid: str imdb id# of movie to remove
    */
    var delete_file;

    if(document.querySelector("div#delete_file > i.c_box").getAttribute("value") === "True"){
        delete_file = true;
    } else {
        delete_file = false;
    }

    function __remove_from_library(imdbid){
        $.post(url_base + "/ajax/remove_movie", {"imdbid": imdbid})
        .done(function(response){
            if(response["response"] === true){
                $.notify({message: response["message"]});
                $movie_list.querySelector(`li[data-imdbid="${imdbid}"]`).outerHTML = "";
                $movie_status_modal.modal("hide");
            } else {
                $.notify({message: response["error"]}, {type: "danger"})
            }

            var index = cached_movies.map(function(e){
                return e.imdbid;
            }).indexOf(imdbid);
            cached_movies.splice(index, 1);

            $movie_status_modal.modal("hide");

        })
        .fail(notify_error);
    }

    if(delete_file){
        $.post(url_base + "/ajax/delete_movie_file", {"imdbid": imdbid})
        .done(function(response){
            if(response["response"] === true){
                $.notify({message: response["message"]}, {type: "success"});
            } else {
                $.notify({message: response["error"]}, {type: "danger"});
            }
        })
        .fail(notify_error)
        .always(function(){
            $delete.modal("hide");
            // Makes sure the file removal is done after file removal
            __remove_from_library(imdbid);
        });
    } else {
        $delete.modal("hide");
        __remove_from_library(imdbid);
    }
}

function update_movie_options(event, elem, imdbid){
    var quality = document.getElementById("movie_quality").value;
    var category = document.getElementById("movie_category").value;
    var status = document.getElementById("movie_status").value;

    var filters = {};
    each(document.querySelectorAll("#settings_advanced input"), function(input){
        filters[input.id] = input.value;
    });

    $.post(url_base + "/ajax/update_movie_options", {
        "quality": quality,
        "category": category,
        "status": status,
        "filters": JSON.stringify(filters),
        "imdbid": imdbid
    })
    .done(function(response){
        if(response["response"]){
            $.notify({message: response["message"]});
            update_movie_status(imdbid, response["status"]);
        } else {
            $.notify({message: response["error"]}, {type: "danger"});
        }
    })
    .fail(notify_error);
}

function manual_download(event, elem, guid, kind, imdbid){
    event.preventDefault();

    var $i = elem.querySelector("i.mdi");
    $i.classList.remove("mdi-download");
    $i.classList.add("mdi-circle");
    $i.classList.add("animated");

    var year = $movie_status_modal.find("div.modal-heade3wr span.year").text();

    $.post(url_base + "/ajax/manual_download", {
        "year": year,
        "guid": guid,
        "kind": kind
    })
    .done(function(response){
        if(response["response"] === true){
            $.notify({message: response["message"]});

            update_movie_status(imdbid, "Snatched");
            update_release_status(guid, "Snatched");
        } else {
            $.notify({message: response["error"]}, {type: "danger"})
        }
    })
    .fail(notify_error)
    .always(function(){
        $i.classList.remove("mdi-circle");
        $i.classList.remove("animated");
        $i.classList.add("mdi-download");
    });
}

function mark_bad(event, elem, guid, imdbid, status){
    /* Mark search result as Bad
    guid: str absolute guid of download
    imdbid: str imdb id# of movie
    */
    event.preventDefault();

    var movie = $movie_status_modal.data("movie");
    if(movie.finished_file && status === "Finished"){
        var modal = format_template(templates.delete_file, {
            guid: guid,
            imdbid: imdbid,
            finished_file: movie.finished_file
        });
        $delete = $(modal);

        $delete.modal("show");
        $movie_status_modal.css("opacity", 0);
        $delete.on("hide.bs.modal", function(){
            $movie_status_modal.css("opacity", 1);
            $delete.remove();
        });
    } else {
        _mark_bad(elem, guid, imdbid);
    }
}

function delete_file_mark_bad(event, elem, guid, imdbid){
    $.post(url_base + "/ajax/delete_movie_file", {"imdbid": imdbid})
    .done(function(response){
        if(response["response"] === true){
            $.notify({message: response["message"]}, {type: "success"});
            $movie_status_modal.data("movie").finished_file = null;
            $movie_status_modal.find("#finished_file_badge").addClass("hidden");
        } else {
            $.notify({message: response["error"]}, {type: "danger"});
        }
    })
    .fail(notify_error)
    .always(function(){
        $delete.modal("hide");
        // Makes sure the release is mark bad after file removal
        elem = document.querySelector(`li.search_result[data-guid="${guid}"] .mdi-cancel`).parentElement;
        _mark_bad(elem, guid, imdbid);
    });
}

function _mark_bad(elem, guid, imdbid){
    var $i = elem.querySelector("i.mdi");

    $i.classList.remove("mdi-cancel");
    $i.classList.add("mdi-circle");
    $i.classList.add("animated");

    $.post(url_base + "/ajax/mark_bad", {
        "guid": guid,
        "imdbid": imdbid,
        "cancel_download": true
    })
    .done(function(response){

        if(response["movie_status"]){
            update_movie_status(imdbid, response["movie_status"]);
        }

        if(response["response"] === true){
            $.notify({message: response["message"]});
            update_release_status(guid, "Bad");
        } else {
            $.notify({message: response["error"]}, {type: "danger"});
        }
    })
    .fail(notify_error)
    .always(function(){
        $i.classList.remove("mdi-circle");
        $i.classList.remove("animated");
        $i.classList.add("mdi-cancel");
    });
}

function update_movie_status(imdbid, status){
    /* Updates movie in Status list to status
    imdbid: str imdb id# of movie to change
    status: str new status of movie
    */
    if(status === "Disabled"){
        status = "Finished"
    }

    var label = document.querySelector(`ul#movie_list > li[data-imdbid="${imdbid}"] span.status`);

    if(label){
        label.textContent = status;
        label.classList = `badge badge-${status_colors[status]} status`;
    }

    var $status_label = $movie_list.querySelector(`li[data-imdbid="${imdbid}"] span.status`);
    $status_label.classList.remove($status_label.innerText);
    $status_label.classList.add(status);
    $status_label.innerText = status;
}

function update_release_status(guid, status){
    /* Updates status label for search result
    guid: str guid of target release
    status: str status to update label to
    */

    var label = document.querySelector(`li.search_result[data-guid="${guid}"] span.status`);

    if(label){
        label.textContent = status;
        label.classList = `badge badge-${status_colors[status]} status`;
    }

}

function swap_settings(event){
    // Changes modal between basic and advanced settings

    var $i = event.target;
    var $basic = document.getElementById("settings_basic");
    var $advanced = document.getElementById("settings_advanced");

    if($i.dataset.open === "basic"){
        $i.style.transform = "rotate(-135deg)";
        $advanced.classList.remove("hide");
        $basic.classList.add("hide");
        $i.dataset.open = "advanced";
    } else {
        $i.style.transform = "rotate(0deg)";
        $advanced.classList.add("hide");
        $basic.classList.remove("hide");
        $i.dataset.open = "basic";
    }

}

function showLoader(){
    $(".loader").fadeIn("slow");
}

function hideLoader(){
    $(".loader").fadeOut("slow");
}
