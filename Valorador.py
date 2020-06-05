# -*- coding: utf-8 -*-

from multiprocessing import Process, Queue
from string import Template
import socket
import sys
import random
import uuid
import datetime

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
port = 9040

agn = Namespace(Constants.ONTOLOGY)

# Contador de mensajes
mss_cnt = 0

# Datos del Agente

Valorador = Agent('Valorador',
                       agn.Valorador,
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
    """
    Entrypoint de comunicacion
    """
    req = Graph()
    req.parse(data=request.args['content'])
    message_properties = get_message_properties(req)
    content = message_properties['content']
    accion = str(req.value(subject=content, predicate=RDF.type))
    logging.info('Accion: ' + accion)
    if accion == 'Pedir_Feedback':
        return pedir_feedback(req, content)
    elif accion == 'Enviar_Feedback':
        return enviar_feedback(req, content)
    elif accion == 'Recibir_Recomendaciones':
        return recomendaciones(req, content)

def pedir_feedback(req, content):
    logging.info("Pedimos feedback")
    id_usuario = req.value(subject=content, predicate=agn['id_usuario'])
    logging.info("ID Usuario = " + str(id_usuario))
    prod = Graph()
    prod = get_prod_usuario(id_usuario)
    return prod

def get_prod_usuario(id_usuario):
    historial_compras = Graph().parse('./data/historial_compras.owl')
    logging.info("ID Usuario en la busqueda " + id_usuario)
    sparql_query = Template('''
        SELECT DISTINCT ?compra ?product ?id ?id_usuario
        WHERE {
            ?compra rdf:type ?type_prod .
            ?compra ns:product ?product .
            ?compra ns:id_usuario ?id_usuario .
            ?compra ns:id ?id .
            FILTER (
                ?id_usuario = '$id_usuario'
            )
        }
        LIMIT 5
    ''').substitute(dict(
        id_usuario = id_usuario
    ))
    result = historial_compras.query(
        sparql_query,
        initNs=dict(
            rdf=RDF,
            ns=agn,
    ))
    i = 0
    result_message = Graph()
    for x in result:
        producto = agn[x.product + '_' + i]
        logging.info(x.product)
        logging.info(x.id)
        result_message.add((producto, RDF.type, agn.product))
        result_message.add((producto, agn.nombre, x.product))
        result_message.add((producto, agn.id_compra, x.id))
        i = i + 1
    return result_message.serialize(format='xml')

def enviar_feedback(req, content):
    logging.info("Guardamos feedback")
    productos = Graph().parse('./data/product.owl')

    for producto in req.subjects(RDF.type, agn.product):
        nombre = req.value(subject=producto, predicate=agn.nombre)
        logging.info(nombre)
        valoracion = float(req.value(subject=producto, predicate=agn.valoracion))
        logging.info(valoracion)
        pontp = Namespace("http://www.products.org/ontology/property/")
        producto = next(productos.subjects(pontp.nombre, nombre))
        num_valoraciones = int(productos.value(producto, pontp.numeroValoraciones))
        valoracion_total = float(productos.value(producto, pontp.valoracionTotal))
        num_valoraciones += 1
        valoracion_total = (valoracion_total+valoracion)
        logging.info('Nueva valoracion total: ' + str(valoracion_total))
        productos.remove((producto, pontp.numeroValoraciones, None))
        productos.add((producto, pontp.numeroValoraciones, Literal(num_valoraciones)))
        productos.remove((producto, pontp.valoracionTotal, None))
        productos.add((producto, pontp.valoracionTotal, Literal(valoracion_total)))
        productos.serialize('./data/product.owl')
    return Graph().serialize(format='xml')

def recomendaciones(req, content):
    logging.info("Generamos recomendaciones")
    id_usuario = req.value(subject=content, predicate=agn['id_usuario'])
    logging.info("ID Usuario = " + str(id_usuario))

    historial_compras = Graph().parse('./data/historial_compras.owl')
    productos = Graph().parse('./data/product.owl')
    marcas = []
    sparql_query = Template('''
        SELECT DISTINCT ?compra ?product ?id ?id_usuario
        WHERE {
            ?compra rdf:type ?type_prod .
            ?compra ns:product ?product .
            ?compra ns:id_usuario ?id_usuario .
            FILTER (
                ?id_usuario = '$id_usuario'
            )
        }
    ''').substitute(dict(
        id_usuario = id_usuario
    ))
    result = historial_compras.query(
        sparql_query,
        initNs=dict(
            rdf=RDF,
            ns=agn,
    ))

    for x in result:
        nombreProd = str(x.product)
        logging.info("Nombre producto: " + str(nombreProd))
        sparql_query2 = Template('''
            SELECT DISTINCT ?producto ?nombre ?precio ?peso ?tieneMarca ?tipo ?valoracionTotal ?numeroValoraciones
            WHERE {
                ?producto rdf:type ?tipo .
                ?producto pontp:nombre ?nombre .
                ?producto pontp:precio ?precio .
                ?producto pontp:peso ?peso .
                ?producto pontp:tieneMarca ?tieneMarca .
                ?producto pontp:valoracionTotal ?valoracionTotal .
                ?producto pontp:numeroValoraciones ?numeroValoraciones .
                FILTER (
                    ?nombre = '$nombre'
                )
            }
        ''').substitute(dict(
            nombre = nombreProd
        ))
        result2 = productos.query(
            sparql_query2,
            initNs=dict(
                rdf=RDF,
                pontp=Namespace("http://www.products.org/ontology/property/")
        ))
        for x2 in result2:
            tieneMarca = str(x2.tieneMarca)
            logging.info(tieneMarca)
            exists = 0
            for marca in marcas:
                if tieneMarca == marca[0]:
                    marca[1] += 1
                    exists = 1
            if exists == 0:
                marcas.append([tieneMarca, 1])
    logging.info(marcas)

    topVal = 0
    topMarca = 'xd'
    for marca in marcas:
        logging.info("marca: " + str(marca[1]))
        logging.info("topVal: " + str(topVal))
        if marca[1] > topVal:
            topMarca = marca[0]
            topVal = marca[1]
    logging.info(topMarca)

    productos = Graph().parse('./data/product.owl')
    sparql_query = Template('''
        SELECT DISTINCT ?producto ?nombre ?precio ?peso ?tipo ?tieneMarca ?valoracionTotal ?numeroValoraciones
        WHERE {
            ?producto rdf:type ?tipo .
            ?producto pontp:nombre ?nombre .
            ?producto pontp:precio ?precio .
            ?producto pontp:peso ?peso .
            ?producto pontp:tieneMarca ?tieneMarca .
            ?producto pontp:valoracionTotal ?valoracionTotal .
            ?producto pontp:numeroValoraciones ?numeroValoraciones .
            FILTER (
                str(?tieneMarca) = '$topMarca' 
            )
        }
    ''').substitute(dict(
            topMarca = topMarca
    ))
    result3 = productos.query(
        sparql_query,
        initNs=dict(
            rdf=RDF,
            pontp=Namespace("http://www.products.org/ontology/property/")
        )
    )
    result_message = Graph()
    for x3 in result3:
        logging.info("Nombre producto añadido: " + str(x3.nombre))
        result_message.add((x3.producto, RDF.type, x3.tipo))
        result_message.add((x3.producto, agn.nombre, x3.nombre))
        result_message.add((x3.producto, agn.peso, x3.peso))
        result_message.add((x3.producto, agn.precio, x3.precio))
        result_message.add((x3.producto, agn.tieneMarca, Literal(x3.tieneMarca)))
        result_message.add((x3.producto, agn.valoracionTotal, Literal(x3.valoracionTotal)))
        result_message.add((x3.producto, agn.numeroValoraciones, Literal(x3.numeroValoraciones)))
    return result_message.serialize(format='xml')

    
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
    Valorador.register_agent(DirectoryAgent)
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


