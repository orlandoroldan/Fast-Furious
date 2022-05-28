from metro import *
import osmnx as ox
import os
import pickle                       # per guardar graf osmnx en un fitxer i no haver de baixar-lo cada cop. Serveix també per obrir el fitxer amb el graf quan ja ha set descarregat.


######################
#   Tipus de dades   #
######################

CityGraph: TypeAlias = nx.Graph

OsmnxGraph: TypeAlias = nx.MultiDiGraph

NodeID: TypeAlias = int

Path: TypeAlias = List[NodeID]                   # tots els nodes tenen identificadors enters

#############################
#  Funcions implementades   #
#############################

######################
#  Obtenció del graf #
######################

def get_osmnx_graph() -> OsmnxGraph:
    """Obté i retorna el graf dels carrers de Barcelona de la web mitjançant osmnx."""

    graph = ox.graph_from_place('Barcelona', network_type = 'walk', simplify=True)
    
    # eliminem la informació de geometria dels atributs perquè ocupa molt espai i no la necessitem
    for u, v, key, geom in graph.edges(data = "geometry", keys = True):
        if geom is not None:
            del(graph[u][v][key]["geometry"])
    
    return graph
        
def save_osmnx_graph(g: OsmnxGraph, filename: str) -> None:
    """Guarda el graf de carrers al fitxer de nom "filename" per poder-hi accedir futurament sense carregar-lo constantment de la web."""

    pickle_out = open(filename, 'wb')
    pickle.dump(g, pickle_out)
    pickle_out.close()


def load_osmnx_graph(filename: str) -> OsmnxGraph:
    """Retorna el graf de carrers. En cas que sigui el primer cop que intentem accedir a aquest graf, 
    se'l descarrega de la web. Si no, accedeix al fitxer de nom filename on està guardat."""

    if not os.path.exists(filename):
        bcn_streets = get_osmnx_graph()
        save_osmnx_graph(bcn_streets, filename)
        return bcn_streets
    
    pickle_in = open(filename, "rb")
    bcn_streets = pickle.load(pickle_in)
    
    return bcn_streets
   

#################
#   Graf city   #
#################


def build_city_graph(g1: OsmnxGraph, g2: MetroGraph) -> CityGraph: 
    """Retorna un graf fusió del graf de Barcelona (carrers) i el graf de metros. Primer recorrem el primer 
    graf (g1, de carrers) afegint al nostre graf de ciutat tots els nodes, arestes i informació rellevant.
    Després fem la unió amb el graf de metro (g2). Finalment, afegim les arestes que connecten els accessos
    amb el graf de ciutat i en retornem el resultat."""
    
    city_graph = nx.Graph()                     # type = CityGraph

    # recorrem el graf g1
    for node, nbrs_dict in g1.adjacency(): 
        city_graph.add_node(node, dtype = "Street", position = Coord(g1.nodes[node]['x'], g1.nodes[node]['y']), color = "black" )    
        # per cada node adjacent i la informació associada a l'aresta entre ells
        for nbr, edgesdict in nbrs_dict.items():
            e_attrib = edgesdict[0]    # e_attrib conté l'atribut de la primera aresta (multigrafs)
            # afegim una aresta entre node i nbr i hi associem tota la informació d'aquesta i el seu tipus.
            if "name" in e_attrib:
                nom = e_attrib["name"]
                if not isinstance(e_attrib["name"], str):
                    nom = nom[0]
            else: nom = "lloc indicat"
            city_graph.add_edge(node, nbr, dtype = "Street", time = set_time("Street", e_attrib["length"]), name=nom, color = "black")

    # unió amb graf de metros
    city_graph = nx.union(g2, city_graph)

    # afegir arestes que connecten els accessos amb la ciutat
    dtype = nx.get_node_attributes(g2, 'dtype') # diccionari amb els tipus
    list_x,list_y, list_a = [], [], []
    for i in g2.nodes:
        if dtype[i] == "Access":
            coords = g2.nodes[i]["position"]
            list_x.append(coords.x)
            list_y.append(coords.y)
            list_a.append(i)
    
    nearest = ox.distance.nearest_nodes(g1, list_x, list_y)
    j = 0
    for i in list_a:
        coords = g2.nodes[i]["position"]
        temps = set_time("Street", haversine(city_graph.nodes[i]["position"], city_graph.nodes[nearest[j]]["position"], unit=Unit.METERS))
        city_graph.add_edge(i, nearest[j], dtype = "Street", time=temps, color = "black")
        j += 1
        
    city_graph.remove_edges_from(nx.selfloop_edges(city_graph)) # esborrem les selfloops del graf

    return city_graph

############
#   Path   #
############

def get_metro_path_description(g: CityGraph, p: Path, i: int, description: str):
    first_station = g.nodes[p[i]]["name"]
    metro_line = g.nodes[p[i]]["line"]
    current_edge_type = g[p[i]][p[i+1]]["dtype"]

    while current_edge_type == "Tram":
        i += 1
        current_edge_type = g[p[i]][p[i+1]]["dtype"]
    last_station = g.nodes[p[i]]["name"]
    description += "🚇 Ves des de l'estació " + first_station + \
        " fins a " + last_station + " amb la linia " + metro_line + ". "
    return i


def get_path_description(g: CityGraph, p: Path):
    description = ""               # descripció del path
    i = 0                           # posició en el path
    
    while i < (len(p)-1):
        current_edge_type = g[p[i]][p[i+1]]["dtype"]    # tipus de l'aresta en la qual ens trobem

        if current_edge_type == "Street":
            starting_street = g[p[i]][p[i+1]]["name"]
            while i < len(p)-2 and current_edge_type == "Street":
                i += 1
                current_edge_type = g[p[i]][p[i+1]]["dtype"]
            ending_street = g[p[i-2]][p[i-1]]["name"]
            description += "🚶 Camina des de: " + starting_street + " fins a: " + ending_street + ". "
            
        if current_edge_type == "Access":
            metro_entry = g.nodes[p[i]]["name"][0]
            description += "Entra al metro per l'accés " + metro_entry + ". "
            i += 1
            current_edge_type = g[p[i]][p[i+1]]["dtype"]
            # s'entra per un accés i es surt per un accés
            while current_edge_type != "Access":
                i = get_metro_path_description(g, p, i, description)
                if g[p[i]][p[i+1]]["dtype"] == "Enllaç":
                    description += "Fes un transbordament. "
                    i += 1
                current_edge_type = g[p[i]][p[i+1]]["dtype"]
            i += 1
            metro_exit = g.nodes[p[i]]["name"][0]
            description += "Surt del metro per l'accés " + metro_exit + ".\n"
        i += 1

    return description

def get_time_path(g: CityGraph, p: Path):
    """Retorna el temps que es triga en recórrer un cert path."""

    time = 0
    for i in range(len(p)-1):
        time += g[p[i]][p[i+1]]["time"]
    return time

# Recordem que l'estructura de Coord és (longitud, latitud)
def find_path(ox_g: OsmnxGraph, g: CityGraph, src: Coord, dst: Coord) -> Path:
  """Retorna el camí més curt des de les coordenades de sortida fins les coordenades de destí.
  Utilitza l'OsmnxGraph per trobar l'ID del node més proper a aquestes coordenades i empra el
  city graph per calcular el camí més curt que les connecta."""

  nearest_src = ox.distance.nearest_nodes(ox_g, src.x, src.y)
  nearest_dst = ox.distance.nearest_nodes(ox_g, dst.x, dst.y)
  return nx.shortest_path(g, nearest_src, nearest_dst, weight="time")


#################
#   Imatges     #
#################

# SHOW TOT EL GRAPH
def show(g: CityGraph) -> None:
    """Mostra una imatge del citygraph."""

    nx.draw(g, pos=nx.get_node_attributes(g, 'position'), node_size=5, width=1, node_color=get_node_colors(g), edge_color=get_edge_colors(g))
    plt.show()


# PLOT DE TOT EL GRAPH
def plot(g: CityGraph, filename: str) -> None:
    """Guarda al fitxer "filename" un plot del graf de ciutat amb la ciutat de Barcelona de fons. S'usa staticmap."""

    m = StaticMap(1200, 800, 0)
    for u in g.nodes:
        coord_u = g.nodes[u]['position']
        color = g.nodes[u]['color']
        marker = CircleMarker(coord_u, color, 2)
        m.add_marker(marker)
    for v in g.edges:
        coord_u, coord_v = g.nodes[v[0]]['position'], g.nodes[v[1]]['position']
        color = g.edges[v]['color']
        line = Line({coord_u, coord_v}, color, 1)
        m.add_line(line)

    image = m.render()
    image.save(filename)

    
# p path és una llista de nodes que tenen
def plot_path(g: CityGraph, p: Path, filename: str) -> None:
    """Guarda al fitxer "filename" un plot del path p amb la ciutat de Barcelona de fons. S'usa staticmap"""

    m = StaticMap(1200, 800, 0)
    marker = CircleMarker(g.nodes[p[0]]["position"], g.nodes[p[0]]["color"], 10)
    m.add_marker(marker)
    marker = CircleMarker(g.nodes[p[-1]]["position"], g.nodes[p[-1]]["color"], 10)
    m.add_marker(marker)

    for i in range(len(p)-1):
        coord1, coord2 = g.nodes[p[i]]["position"], g.nodes[p[i + 1]]["position"]
        color = "black"     # color per default (carrers)
        if g.nodes[p[i]]["dtype"] != "Street": 
            color = g[p[i]][p[i+1]]["color"]
        line = Line({coord1, coord2}, color, 5)
        m.add_line(line)

    image = m.render()
    image.save(filename)


g1 = load_osmnx_graph("barcelona.grf")
g2 = build_city_graph(g1, get_metro_graph())
src, dst = Coord(2.1164254127729225, 41.386597467879106), Coord(2.1623322249990866, 41.39445328391226)
path = find_path(g1, g2, src, dst)
print(get_path_description(g2, path))

