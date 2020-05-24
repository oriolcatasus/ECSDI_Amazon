# -*- coding: utf-8 -*-

from multiprocessing import Process, Queue
from string import Template
import socket
import sys
import uuid

from rdflib import Namespace, Graph, RDF
from rdflib.namespace import FOAF
from rdflib.term import Literal
from flask import Flask, request

from AgentUtil.ACLMessages import get_message_properties, build_message, send_message
from AgentUtil.FlaskServer import shutdown_server
from AgentUtil.OntoNamespaces import ACL
from AgentUtil.Agent import Agent
import requests

import logging
logging.basicConfig(level=logging.DEBUG)

import Constants.Constants as Constants

# Configuration stuff
hostname = '127.0.1.1'
port = 9003

agn = Namespace(Constants.ONTOLOGY)

# Contador de mensajes
mss_cnt = 0

# Datos de los lotes
peso_lote = 1000.0
num_lotes = 0
max_lotes = 2

# Datos del Agente

CentroLogistico = Agent('CentroLogistico',
                       agn.CentroLogistico,
                       'http://%s:%d/comm' % (hostname, port),
                       'http://%s:%d/Stop' % (hostname, port))

# Directory agent address
DirectoryAgent = Agent('DirectoryAgent',
                       agn.Directory,
                       'http://%s:9000/Register' % hostname,
                       'http://%s:9000/Stop' % hostname)


# Global triplestore graph
dsgraph = Graph()

cola1 = Queue()

# Flask stuff
app = Flask(__name__)


@app.route("/comm")
def comunicacion():
    req = Graph()
    req.parse(data=request.args['content'])
    message_properties = get_message_properties(req)
    content = message_properties['content']
    accion = str(req.value(subject=content, predicate=RDF.type))
    logging.info('Accion: ' + accion)
    if accion == 'Empezar_Envio_Compra':        
        return empezar_envio_compra(req, content)


def empezar_envio_compra(req, content):
    global mss_cnt
    global peso_lote
    global max_lotes

    mss_cnt = mss_cnt + 1
    # Datos de los lotes
    lotes_graph = Graph()
    try:
        lotes_graph.parse('./data/lotes.owl')
    except Exception as e:
        logging.info('No lotes graph found')
    # Id compra
    id_compra = int(req.value(subject=content, predicate=agn.id_compra))
    literal_id_compra = Literal(id_compra)
    str_id_compra = str(id_compra)
    logging.info('id_compra: ' + str_id_compra)
    compra = agn['compra_' + str_id_compra]
    lotes_graph.add((compra, RDF.type, agn.compra))
    lotes_graph.add((compra, agn.id_compra, literal_id_compra))
    # Codigo postal
    codigo_postal = str(req.value(subject=content, predicate=agn.codigo_postal))
    logging.info('codigo postal: ' + codigo_postal)
    lotes_graph.add((compra, agn.codigo_postal, Literal(codigo_postal)))
    # Direccion de envio
    direccion = str(req.value(subject=content, predicate=agn.direccion))
    logging.info('direccion: ' + direccion)
    lotes_graph.add((compra, agn.direccion, Literal(direccion)))
    # Total peso compra
    total_peso = float(req.value(subject=content, predicate=agn.total_peso))
    logging.info('total peso: ' + str(total_peso))
    lotes_graph.add((compra, agn.total_peso, Literal(total_peso)))
    # Productos
    for producto in req.subjects(RDF.type, agn.product):
        nombre = req.value(subject=producto, predicate=agn.nombre)
        logging.info(nombre)
        lotes_graph.add((producto, RDF.type, agn.product))
        lotes_graph.add((producto, agn.nombre, nombre))
        lotes_graph.add((producto, agn.id_compra, literal_id_compra))
    # Lotes
    nuevo_lote = False
    if total_peso >= peso_lote: # Si el pedido ya es todo un lote
        id_lote = uuid.uuid4().int
        lotes_graph.add((compra, agn.lote, Literal(id_lote)))
        nuevo_lote = True
    else:
        lotes_graph.add((compra, agn.lote, Literal(-1)))
        nuevo_lote = distribuir_lotes(lotes_graph, codigo_postal)
    # Si podemos, enviamos los lotes
    if nuevo_lote and get_numero_lotes(lotes_graph) >= max_lotes:
        transportista = negociar(codigo_postal)
        transportar(transportista, lotes_graph)
    lotes_graph.serialize('./data/lotes.owl')
    return Graph().serialize(format='xml')

def distribuir_lotes(lotes_graph, codigo_postal):
    global peso_lote

    sparql_query = Template('''
        SELECT (SUM(?total_peso) as ?sum) ?compra ?codigo_postal ?lote
        WHERE {
            ?compra rdf:type ?type_compra .
            ?compra ns:codigo_postal ?codigo_postal .
            ?compra ns:total_peso ?total_peso .
            ?compra ns:lote ?lote .
            FILTER (
                ?codigo_postal = '$codigo_postal' &&
                ?lote = -1
            )
        }
    ''').substitute(dict(
        codigo_postal=codigo_postal       
    ))
    result = lotes_graph.query(
        sparql_query,
        initNs=dict(
            rdf=RDF,
            ns=agn
        )
    )
    total_peso_lote = float(next(iter(result)).sum)
    logging.info('Total peso hasta ahora: ' + str(total_peso_lote))
    nuevo_lote = total_peso_lote >= peso_lote
    if nuevo_lote:
        id_lote = Literal(uuid.uuid4().int)
        for compra in lotes_graph.subjects(RDF.type, agn.compra):
            lote_producto = int(lotes_graph.value(compra, agn.lote))
            codig_postal_producto = str(lotes_graph.value(compra, agn.codigo_postal))
            if lote_producto == -1 and codig_postal_producto == codigo_postal:
                lotes_graph.remove((compra, agn.lote))
                lotes_graph.add((compra, agn.lote, id_lote))
    return nuevo_lote

def get_numero_lotes(lotes_graph):
    sparql_query = '''
        SELECT (COUNT(DISTINCT ?lote) as ?cnt) ?compra ?lote
        WHERE {
            ?compra rdf:type ?type_compra .
            ?compra ns:lote ?lote .
            FILTER ( 
                ?lote != -1
            )
        }
    '''
    result = lotes_graph.query(
        sparql_query,
        initNs=dict(
            rdf=RDF,
            ns=agn
        )
    )
    num_lotes = int(next(iter(result)).cnt)
    logging.info('num_lotes: ' + str(num_lotes))
    return num_lotes

def negociar(codigo_postal):
    global mss_cnt

    mss_cnt = mss_cnt + 1
    transportista = CentroLogistico.directory_search(DirectoryAgent, agn.Transportista)
    transportista_a_enviar = transportista
    ofertaT1 = 0
    ofertaT2 = 0
    transportista2 = CentroLogistico.directory_search(DirectoryAgent, agn.Transportista2)
    gNegociar = Graph()
    negociar = agn['negociar_' + str(mss_cnt)]
    gNegociar.add((negociar, RDF.type, Literal('Negociar')))
    gNegociar.add((negociar, agn.codigo_postal, Literal(codigo_postal)))
    message = build_message(
        gNegociar,
        perf=Literal('request'),
        sender=CentroLogistico.uri,
        receiver=transportista.uri,
        msgcnt=mss_cnt,
        content=negociar
    )
    response = send_message(message, transportista.address)
    for item in response.subjects(RDF.type, Literal('Oferta_Transportista')):
        logging.info("BUCLE 1")
        for oferta in response.objects(item, agn.oferta):
            logging.info("BUCLE 2")
            ofertaT1 = oferta
            logging.info('Oferta1: ' + str(ofertaT1))
    response2 = send_message(message, transportista2.address)
    for item in response2.subjects(RDF.type, Literal('Oferta_Transportista')):
        logging.info("BUCLE 1")
        for oferta in response2.objects(item, agn.oferta):
            logging.info("BUCLE 2")
            ofertaT2 = oferta
            logging.info('Oferta2: ' + str(ofertaT2))
    if (ofertaT2 < ofertaT1) :
        transportista_a_enviar = transportista2
    logging.info("Escogemos transportista " + str(transportista_a_enviar.address))
    return transportista_a_enviar


def transportar(transportista, lotes_graph):
    global mss_cnt
    
    mss_cnt = mss_cnt + 1
    logging.info('Aceptamos oferta')
    gTransportar = Graph()
    transportar = agn['transportar_' + str(mss_cnt)]
    gTransportar.add((transportar, RDF.type, Literal('Transportar')))
    for compra in lotes_graph.subjects(RDF.type, agn.compra):
        lote = int(lotes_graph.value(compra, agn.lote))
        if lote != -1:
            # Enviar compra
            gTransportar.add((compra, RDF.type, agn.compra))
            gTransportar.add((compra, agn.lote, Literal(lote)))
            codigo_postal = str(lotes_graph.value(compra, agn.codigo_postal))
            gTransportar.add((compra, agn.codigo_postal, Literal(codigo_postal)))            
            total_peso = float(lotes_graph.value(compra, agn.total_peso))
            gTransportar.add((compra, agn.total_peso, Literal(total_peso)))
            direccion = str(lotes_graph.value(compra, agn.direccion))
            gTransportar.add((compra, agn.direccion, Literal(direccion)))
            # Borrar compra de los productos para enviar
            id_compra = int(lotes_graph.value(compra, agn.id_compra))
            lotes_graph.remove((compra, None, None))
            borrar_productos_enviados(lotes_graph, id_compra)
    # Enviar mensaje
    message = build_message(
        gTransportar,
        perf=Literal('request'),
        sender=CentroLogistico.uri,
        receiver=transportista.uri,
        msgcnt=mss_cnt,
        content=transportar
    )
    send_message(message, transportista.address)

def borrar_productos_enviados(lotes_graph, id_compra):
    for producto in lotes_graph.subjects(RDF.type, agn.product):
        producto_id_compra = int(lotes_graph.value(producto, agn.id_compra))
        if (id_compra == producto_id_compra):
            lotes_graph.remove((producto, None, None))


@app.route("/Stop")
def stop():
    """
    Entrypoint que para el agente

    :return:
    """
    tidyup()
    shutdown_server()
    return "Parando Servidor"


def tidyup():
    """
    Acciones previas a parar el agente

    """
    pass


def agentbehavior1(cola):
    """
    Un comportamiento del agente

    :return:
    """
    CentroLogistico.register_agent(DirectoryAgent)
    pass


if __name__ == '__main__':
    # Ponemos en marcha los behaviors
    ab1 = Process(target=agentbehavior1, args=(cola1,))
    ab1.start()

    # Ponemos en marcha el servidor
    app.run(host=hostname, port=port)

    # Esperamos a que acaben los behaviors
    ab1.join()
    print('The End')
