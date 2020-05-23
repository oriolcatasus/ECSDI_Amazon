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

#Pedidos por envio
max_pedidos = 5

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
    global max_pedidos
    global mss_cnt

    mss_cnt = mss_cnt + 1
    codigo_postal = str(req.value(subject=content, predicate=agn.codigo_postal))
    logging.info('codigo postal: ' + codigo_postal)
    direccion = str(req.value(subject=content, predicate=agn.direccion))
    logging.info('direccion: ' + direccion)
    for item in req.subjects(RDF.type, agn.product):
        nombre=str(req.value(subject=item, predicate=agn.nombre))
        logging.info(nombre)

    lotes_graph = Graph()
    try:
        lotes_graph.parse('./data/lotes.owl')
    except Exception as e:
        logging.info('No lotes graph found')
        #cp = agn[codigo_postal]
        #lotes_graph.add((cp, RDF.type, Literal('Codigo_Postal')))
    add_products_to_lote(req, lotes_graph, codigo_postal)
    logging.info(codigo_postal)
    sparql_query = Template('''
        SELECT (COUNT(*) as ?cnt)?producto ?codigo_postal
        WHERE {
            ?producto rdf:type ?type_prod .
            ?producto ns:codigo_postal ?codigo_postal .
            FILTER (
                ?codigo_postal = '$codigo_postal'
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
    logging.info('Result:')
    for x in result:
        logging.info(x.cnt)
        logging.info(max_pedidos)
        if (int(x.cnt) >= max_pedidos):
            logging.info('Entra if')
            transportista = negociar(codigo_postal)
            transportar(codigo_postal, transportista, lotes_graph)
    lotes_graph.serialize('./data/lotes.owl')
    return Graph().serialize(format='xml')

def add_products_to_lote(req, lotes_graph, codigo_postal):
    global mss_cnt

    i = 1
    for item in req.subjects(RDF.type, agn.product):
        nombre=req.value(subject=item, predicate=agn.nombre)
        precio=req.value(subject=item, predicate=agn.precio)
        new_item = agn[nombre + '_' + str(mss_cnt) + '_' + str(i)]
        lotes_graph.add((new_item, RDF.type, agn.product))
        lotes_graph.add((new_item, agn.nombre, Literal(nombre)))
        lotes_graph.add((new_item, agn.codigo_postal, Literal(codigo_postal)))
        lotes_graph.add((new_item, agn.precio, Literal(precio)))
        i = i+1

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
    #subjects = list(response.subjects(RDF.type, Literal('Oferta_Transportista')))
    #precio = response.value((subjects[0], agn.oferta))
    #logging.info('Oferta: ' + str(precio))
    if (ofertaT2 < ofertaT1) :
        transportista_a_enviar = transportista2
    logging.info("Escogemos transportista " + str(transportista_a_enviar.address))
    return transportista_a_enviar


def transportar(codigo_postal, transportista, lotes_graph):
    global mss_cnt
    
    mss_cnt = mss_cnt + 1
    logging.info('Aceptamos oferta')
    gTransportar = Graph()
    transportar = agn['transportar_' + str(mss_cnt)]
    gTransportar.add((transportar, RDF.type, Literal('Transportar')))
    gTransportar.add((transportar, agn.codigo_postal, Literal(codigo_postal)))
    sparql_query = Template('''
        SELECT ?producto ?codigo_postal ?nombre ?precio
        WHERE {
            ?producto rdf:type ?type_prod .
            ?producto ns:codigo_postal ?codigo_postal .
            ?producto ns:nombre ?nombre .
            ?producto ns:precio ?precio .
            FILTER (
                ?codigo_postal = '$codigo_postal'
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
    sum_preu = 0
    for x in result:
        gTransportar.add((x.producto, RDF.type, agn.product))
        gTransportar.add((x.producto, agn.nombre, x.nombre))
        sum_preu += int(x.precio)
        lotes_graph.remove((x.producto, None, None))
    logging.info("Precio productos = " + str(sum_preu))
    message = build_message(
        gTransportar,
        perf=Literal('request'),
        sender=CentroLogistico.uri,
        receiver=transportista.uri,
        msgcnt=mss_cnt,
        content=transportar
    )
    send_message(message, transportista.address)


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
